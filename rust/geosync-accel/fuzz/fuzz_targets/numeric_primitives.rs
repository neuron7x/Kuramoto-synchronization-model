#![no_main]

use geosync_accel::{convolve_core, quantiles_core, sliding_windows_core, ConvolutionMode};
use libfuzzer_sys::fuzz_target;

fn read_f64(bytes: &[u8]) -> f64 {
    let mut raw = [0u8; 8];
    raw.copy_from_slice(bytes);
    let value = f64::from_le_bytes(raw);
    if value.is_finite() {
        value.clamp(-1.0e6, 1.0e6)
    } else {
        0.0
    }
}

fn read_vec(bytes: &[u8], len: usize) -> Vec<f64> {
    bytes.chunks_exact(8).take(len).map(read_f64).collect()
}

fuzz_target!(|data: &[u8]| {
    if data.len() < 18 {
        return;
    }

    let signal_len = (data[0] as usize % 32) + 1;
    let kernel_len = (data[1] as usize % 32) + 1;
    let needed = 2 + (signal_len + kernel_len) * 8;
    if data.len() < needed {
        return;
    }

    let signal_start = 2;
    let kernel_start = signal_start + signal_len * 8;
    let signal = read_vec(&data[signal_start..kernel_start], signal_len);
    let kernel = read_vec(&data[kernel_start..needed], kernel_len);

    let _ = sliding_windows_core(
        &signal,
        (data[2] as usize % 16) + 1,
        (data[3] as usize % 8) + 1,
    );
    let _ = quantiles_core(&signal, &[0.0, 0.25, 0.5, 0.75, 1.0]);
    let _ = convolve_core(&signal, &kernel, ConvolutionMode::Full);
    let _ = convolve_core(&signal, &kernel, ConvolutionMode::Same);
    let _ = convolve_core(&signal, &kernel, ConvolutionMode::Valid);
});
