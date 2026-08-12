//! High-performance numeric primitives shared between the Rust and Python
//! parts of TradePulse.
//!
//! The crate exposes low-level `*_core` functions implemented in safe Rust
//! alongside thin PyO3 bindings that power the Python module.  The public API
//! is intentionally minimal and focuses on:
//!
//! * Sliding window extraction over large contiguous slices.
//! * Quantile estimation with linear interpolation.
//! * One-dimensional convolution supporting the common NumPy modes.
//!
//! Keeping the algorithms and the bindings in the same crate makes it easy to
//! share benchmarks and guarantees that the behaviour is identical between the
//! Rust and Python entry points.

use numpy::ndarray::Array2;
use numpy::{PyArray1, PyArray2, PyReadonlyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::PyErr;
use std::{borrow::Cow, cmp::Ordering, fmt};

/// Error type returned by numeric primitives when the input configuration is
/// invalid.
#[derive(Debug, Clone)]
pub enum NumericError {
    /// Raised when a sliding window has size zero.
    InvalidWindow,
    /// Raised when the requested sliding step has size zero.
    InvalidStep,
    /// Raised when an input slice is empty but a value is required.
    EmptyInput { name: &'static str },
    /// Raised when a probability is not finite (`NaN` or infinite).
    ProbabilityNotFinite(f64),
    /// Raised when a probability falls outside the `[0, 1]` interval.
    ProbabilityOutOfRange(f64),
    /// Raised when a convolution mode other than `full`, `same` or `valid`
    /// is requested.
    UnsupportedMode(String),
}

impl fmt::Display for NumericError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            NumericError::InvalidWindow => write!(f, "window must be greater than zero"),
            NumericError::InvalidStep => write!(f, "step must be greater than zero"),
            NumericError::EmptyInput { name } => write!(f, "{name} must not be empty"),
            NumericError::ProbabilityNotFinite(value) => {
                write!(f, "probability {value} must be finite")
            }
            NumericError::ProbabilityOutOfRange(value) => {
                write!(f, "probability {value} outside [0, 1]")
            }
            NumericError::UnsupportedMode(mode) => {
                write!(f, "unsupported convolution mode '{mode}'")
            }
        }
    }
}

impl std::error::Error for NumericError {}

/// Subset of the convolution modes supported by NumPy's `convolve`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConvolutionMode {
    Full,
    Same,
    Valid,
}

impl TryFrom<&str> for ConvolutionMode {
    type Error = NumericError;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        match value {
            "full" => Ok(Self::Full),
            "same" => Ok(Self::Same),
            "valid" => Ok(Self::Valid),
            other => Err(NumericError::UnsupportedMode(other.to_owned())),
        }
    }
}

/// Guard helper that ensures a slice contains at least one element.
fn check_non_empty(array: &[f64], name: &'static str) -> Result<(), NumericError> {
    if array.is_empty() {
        return Err(NumericError::EmptyInput { name });
    }
    Ok(())
}

#[inline]
fn is_sorted_total(data: &[f64]) -> bool {
    data.len() <= 1
        || data
            .windows(2)
            .all(|pair| pair[0].total_cmp(&pair[1]) != Ordering::Greater)
}

/// Compute overlapping sliding windows over a one-dimensional slice.
///
/// The function returns a tuple consisting of the number of windows and a
/// flattened vector that contains the window contents row-major.  A zero length
/// result indicates that the requested window is larger than the input slice.
pub fn sliding_windows_core(
    data: &[f64],
    window: usize,
    step: usize,
) -> Result<(usize, Vec<f64>), NumericError> {
    if window == 0 {
        return Err(NumericError::InvalidWindow);
    }
    if step == 0 {
        return Err(NumericError::InvalidStep);
    }
    if data.len() < window {
        return Ok((0, Vec::new()));
    }
    let windows = ((data.len() - window) / step) + 1;
    let mut values = Vec::with_capacity(windows * window);
    for i in 0..windows {
        let start = i * step;
        values.extend_from_slice(&data[start..start + window]);
    }
    Ok((windows, values))
}

/// Compute linear-interpolated quantiles for a sorted copy of `data`.
///
/// Invalid probabilities are rejected with detailed errors.  Empty inputs
/// return `NaN` values so that downstream callers can handle the missing data
/// according to their needs.
pub fn quantiles_core(data: &[f64], probabilities: &[f64]) -> Result<Vec<f64>, NumericError> {
    for &probability in probabilities {
        if !probability.is_finite() {
            return Err(NumericError::ProbabilityNotFinite(probability));
        }
        if !(0.0..=1.0).contains(&probability) {
            return Err(NumericError::ProbabilityOutOfRange(probability));
        }
    }
    if data.is_empty() {
        return Ok(vec![f64::NAN; probabilities.len()]);
    }
    let values = if is_sorted_total(data) {
        Cow::Borrowed(data)
    } else {
        let mut owned = data.to_vec();
        owned.sort_by(|a, b| a.total_cmp(b));
        Cow::Owned(owned)
    };
    let values = values.as_ref();
    let n = values.len();
    let mut results = Vec::with_capacity(probabilities.len());
    for &probability in probabilities {
        let position = probability * (n as f64 - 1.0);
        let lower_idx = position.floor() as usize;
        let upper_idx = position.ceil() as usize;
        if lower_idx == upper_idx {
            results.push(values[lower_idx]);
        } else {
            let weight = position - lower_idx as f64;
            let lower = values[lower_idx];
            let upper = values[upper_idx];
            results.push(lower + (upper - lower) * weight);
        }
    }
    Ok(results)
}

/// Perform a direct full convolution between `signal` and `kernel`.
///
/// The implementation uses a straightforward time-domain convolution which is
/// efficient for the relatively small kernels used in TradePulse analytics.
pub fn full_convolution(signal: &[f64], kernel: &[f64]) -> Vec<f64> {
    if signal.is_empty() || kernel.is_empty() {
        return Vec::new();
    }

    let output_len = signal.len() + kernel.len() - 1;
    let mut output = vec![0.0; output_len];

    for (signal_idx, &signal_value) in signal.iter().enumerate() {
        for (kernel_idx, &kernel_value) in kernel.iter().enumerate() {
            let output_idx = signal_idx + kernel_idx;
            output[output_idx] = signal_value.mul_add(kernel_value, output[output_idx]);
        }
    }

    output
}

/// Convolve `signal` with `kernel` respecting the requested convolution mode.
///
/// The function mirrors the semantics of `numpy.convolve`, including the
/// `full`, `same` and `valid` modes.  Empty inputs are rejected to help catch
/// configuration errors early in the pipeline.
pub fn convolve_core(
    signal: &[f64],
    kernel: &[f64],
    mode: ConvolutionMode,
) -> Result<Vec<f64>, NumericError> {
    check_non_empty(signal, "signal")?;
    check_non_empty(kernel, "kernel")?;
    let full = full_convolution(signal, kernel);
    let (n, m) = (signal.len(), kernel.len());
    let full_len = full.len();
    let result = match mode {
        ConvolutionMode::Full => full,
        ConvolutionMode::Same => {
            let target = n.max(m);
            let pad = (full_len - target) / 2;
            let start = pad;
            let end = start + target;
            full[start..end].to_vec()
        }
        ConvolutionMode::Valid => {
            let (shorter, longer) = (n.min(m), n.max(m));
            let length = longer - shorter + 1;
            let start = shorter - 1;
            let end = start + length;
            full[start..end].to_vec()
        }
    };
    Ok(result)
}

impl From<NumericError> for PyErr {
    fn from(value: NumericError) -> Self {
        PyValueError::new_err(value.to_string())
    }
}

#[cfg(test)]
mod core_tests {
    use super::*;

    #[test]
    fn full_convolution_matches_reference() {
        let signal = [1.0, 2.0, 3.0];
        let kernel = [0.5, 0.25];
        let expected = vec![0.5, 1.25, 2.0, 0.75];
        assert_eq!(full_convolution(&signal, &kernel), expected);
    }

    #[test]
    fn full_convolution_handles_empty_input() {
        assert!(full_convolution(&[], &[1.0]).is_empty());
        assert!(full_convolution(&[1.0], &[]).is_empty());
    }

    #[test]
    fn sliding_windows_core_rejects_invalid_parameters() {
        assert!(matches!(
            sliding_windows_core(&[1.0, 2.0], 0, 1),
            Err(NumericError::InvalidWindow)
        ));
        assert!(matches!(
            sliding_windows_core(&[1.0, 2.0], 1, 0),
            Err(NumericError::InvalidStep)
        ));
    }

    #[test]
    fn convolve_core_respects_modes() {
        let signal = [1.0, 2.0, 3.0];
        let kernel = [0.5, 0.5];

        let full = convolve_core(&signal, &kernel, ConvolutionMode::Full).unwrap();
        assert_eq!(full, vec![0.5, 1.5, 2.5, 1.5]);

        let same = convolve_core(&signal, &kernel, ConvolutionMode::Same).unwrap();
        assert_eq!(same, vec![0.5, 1.5, 2.5]);

        let valid = convolve_core(&signal, &kernel, ConvolutionMode::Valid).unwrap();
        assert_eq!(valid, vec![1.5, 2.5]);
    }

    #[test]
    fn quantiles_core_sorts_with_total_order() {
        let data = [3.0, f64::NAN, 1.0];
        let probabilities = [0.0, 0.5, 1.0];
        let result = quantiles_core(&data, &probabilities).unwrap();

        assert_eq!(result.len(), 3);
        assert_eq!(result[0], 1.0);
        assert_eq!(result[1], 3.0);
        assert!(result[2].is_nan());
    }

    #[test]
    fn quantiles_core_rejects_non_finite_probability() {
        let err = quantiles_core(&[1.0], &[f64::NAN]).unwrap_err();
        if let NumericError::ProbabilityNotFinite(value) = err {
            assert!(value.is_nan());
        } else {
            panic!("unexpected error variant: {err:?}");
        }
    }

    #[test]
    fn quantiles_core_rejects_out_of_range_probability() {
        let err = quantiles_core(&[1.0], &[-0.1]).unwrap_err();
        assert!(matches!(err, NumericError::ProbabilityOutOfRange(value) if value < 0.0));
    }
}

#[pyfunction]
#[pyo3(text_signature = "(data, window, step, /)")]
/// Return a 2-D NumPy array containing the flattened sliding windows of
/// `data`.
fn sliding_windows<'py>(
    py: Python<'py>,
    data: PyReadonlyArray1<'py, f64>,
    window: usize,
    step: usize,
) -> PyResult<Bound<'py, PyArray2<f64>>> {
    let slice = data.as_slice()?;
    let (rows, values) = sliding_windows_core(slice, window, step)?;
    let array = Array2::from_shape_vec((rows, window), values)
        .map_err(|err| PyValueError::new_err(err.to_string()))?;
    Ok(PyArray2::from_owned_array_bound(py, array))
}

#[pyfunction]
#[pyo3(text_signature = "(data, probabilities, /)")]
/// Return the interpolated quantiles of `data` for the requested
/// `probabilities`.
fn quantiles<'py>(
    py: Python<'py>,
    data: PyReadonlyArray1<'py, f64>,
    probabilities: Vec<f64>,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let slice = data.as_slice()?;
    let result = quantiles_core(slice, &probabilities)?;
    Ok(PyArray1::from_vec_bound(py, result))
}

#[pyfunction]
#[pyo3(text_signature = "(signal, kernel, mode, /)")]
/// Convolve `signal` with `kernel` using the NumPy-compatible `mode`.
fn convolve<'py>(
    py: Python<'py>,
    signal: PyReadonlyArray1<'py, f64>,
    kernel: PyReadonlyArray1<'py, f64>,
    mode: &str,
) -> PyResult<Bound<'py, PyArray1<f64>>> {
    let signal_slice = signal.as_slice()?;
    let kernel_slice = kernel.as_slice()?;
    let mode = ConvolutionMode::try_from(mode)?;
    let result = convolve_core(signal_slice, kernel_slice, mode)?;
    Ok(PyArray1::from_vec_bound(py, result))
}

#[pymodule]
fn tradepulse_accel(py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(sliding_windows, module)?)?;
    module.add_function(wrap_pyfunction!(quantiles, module)?)?;
    module.add_function(wrap_pyfunction!(convolve, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add(
        "__doc__",
        "Rust accelerators for TradePulse numeric primitives",
    )?;
    module.add("PYTHON_IMPLEMENTATION", "rust")?;
    module.add("PYTHON_VERSION", py.version())?;
    Ok(())
}

#[cfg(all(test, feature = "python-tests"))]
mod tests {
    use super::*;
    use numpy::{PyArray2, PyUntypedArrayMethods, ToPyArray};
    use pyo3::types::PyModule;

    #[test]
    fn python_api_roundtrip() {
        pyo3::prepare_freethreaded_python();
        Python::with_gil(|py| -> PyResult<()> {
            let module = PyModule::new_bound(py, "tradepulse_accel")?;
            tradepulse_accel(py, &module)?;

            let data = vec![1.0, 2.0, 3.0, 4.0];
            let sliding = module.call_method1(
                "sliding_windows",
                (data.clone().to_pyarray_bound(py), 2usize, 1usize),
            )?;
            let windows = sliding.downcast::<PyArray2<f64>>()?;
            assert_eq!(windows.shape(), &[3, 2]);

            let quantiles_vec: Vec<f64> = module
                .call_method1(
                    "quantiles",
                    (data.clone().to_pyarray_bound(py), vec![0.5, 1.0]),
                )?
                .extract()?;
            assert_eq!(quantiles_vec.len(), 2);
            assert!((quantiles_vec[0] - 2.5).abs() < f64::EPSILON);
            assert!((quantiles_vec[1] - 4.0).abs() < f64::EPSILON);

            let conv_vec: Vec<f64> = module
                .call_method1(
                    "convolve",
                    (
                        vec![1.0, 2.0, 3.0].to_pyarray_bound(py),
                        vec![0.5, 0.5].to_pyarray_bound(py),
                        "valid",
                    ),
                )?
                .extract()?;
            assert_eq!(conv_vec, vec![1.5, 2.5]);

            Ok(())
        })
        .unwrap();
    }
}
