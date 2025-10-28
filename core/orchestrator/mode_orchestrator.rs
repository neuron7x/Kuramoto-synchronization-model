//! Rust reference for the ModeOrchestrator state machine.
//!
//! The implementation mirrors the Python logic to allow embedders of the
//! low-latency runtime to share the same transition semantics.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ModeState {
    Action,
    Cooldown,
    Rest,
    SafeExit,
}

#[derive(Debug, Clone, Copy)]
pub struct GuardBand {
    pub soft_limit: f64,
    pub hard_limit: f64,
    pub recover_limit: f64,
}

impl GuardBand {
    pub fn validate(self) -> Result<Self, &'static str> {
        if self.recover_limit <= self.soft_limit && self.soft_limit <= self.hard_limit {
            Ok(self)
        } else {
            Err("recover_limit ≤ soft_limit ≤ hard_limit must hold")
        }
    }

    pub fn is_soft_breach(self, value: f64) -> bool {
        value >= self.soft_limit
    }

    pub fn is_hard_breach(self, value: f64) -> bool {
        value >= self.hard_limit
    }

    pub fn is_recovered(self, value: f64) -> bool {
        value <= self.recover_limit
    }
}

#[derive(Debug, Clone, Copy)]
pub struct GuardConfig {
    pub kappa: GuardBand,
    pub var: GuardBand,
    pub max_drawdown: GuardBand,
    pub heat: GuardBand,
}

impl GuardConfig {
    pub fn validate(self) -> Result<Self, &'static str> {
        Ok(Self {
            kappa: self.kappa.validate()?,
            var: self.var.validate()?,
            max_drawdown: self.max_drawdown.validate()?,
            heat: self.heat.validate()?,
        })
    }
}

#[derive(Debug, Clone, Copy)]
pub struct TimeoutConfig {
    pub action_max: f64,
    pub cooldown_min: f64,
    pub rest_min: f64,
    pub cooldown_persistence: f64,
    pub safe_exit_lock: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct DelayBudget {
    pub action_to_cooldown: f64,
    pub cooldown_to_rest: f64,
    pub protective_to_safe_exit: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct MetricsSnapshot {
    pub kappa: f64,
    pub var: f64,
    pub max_drawdown: f64,
    pub heat: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct ModeOrchestratorConfig {
    pub guards: GuardConfig,
    pub timeouts: TimeoutConfig,
    pub delays: DelayBudget,
    pub initial_state: ModeState,
}

#[derive(Debug, Clone)]
pub struct ModeOrchestrator {
    pub config: ModeOrchestratorConfig,
    state: ModeState,
    state_entered_at: Option<f64>,
    last_timestamp: Option<f64>,
}

impl ModeOrchestrator {
    pub fn new(config: ModeOrchestratorConfig) -> Result<Self, &'static str> {
        let ModeOrchestratorConfig {
            guards,
            timeouts,
            delays,
            initial_state,
        } = config;

        let validated_config = ModeOrchestratorConfig {
            guards: guards.validate()?,
            timeouts,
            delays,
            initial_state,
        };

        Ok(Self {
            state: validated_config.initial_state,
            config: validated_config,
            state_entered_at: None,
            last_timestamp: None,
        })
    }

    pub fn state(&self) -> ModeState {
        self.state
    }

    pub fn reset(&mut self, state: ModeState, timestamp: f64) {
        self.state = state;
        self.state_entered_at = Some(timestamp);
        self.last_timestamp = Some(timestamp);
    }

    pub fn update(&mut self, metrics: MetricsSnapshot, timestamp: f64) -> Result<ModeState, &'static str> {
        self.validate_timestamp(timestamp)?;
        if self.state_entered_at.is_none() {
            self.state_entered_at = Some(timestamp);
        }

        let guard = self.config.guards;
        let hard_breach = self.any_guard(metrics, guard, GuardBand::is_hard_breach);
        if hard_breach {
            return Ok(self.transition_to_safe_exit(timestamp));
        }

        let soft_breach = self.any_guard(metrics, guard, GuardBand::is_soft_breach);
        let recovered = self.all_guard(metrics, guard, GuardBand::is_recovered);
        let elapsed = timestamp - self.state_entered_at.unwrap_or(timestamp);

        match self.state {
            ModeState::Action => {
                if soft_breach || elapsed >= self.config.timeouts.action_max {
                    return Ok(self.transition(ModeState::Cooldown, timestamp));
                }
            }
            ModeState::Cooldown => {
                if recovered && elapsed >= self.config.timeouts.cooldown_min {
                    return Ok(self.transition(ModeState::Action, timestamp));
                }
                if !recovered && elapsed >= self.config.timeouts.cooldown_persistence {
                    return Ok(self.transition(ModeState::Rest, timestamp));
                }
            }
            ModeState::Rest => {
                if recovered && elapsed >= self.config.timeouts.rest_min {
                    return Ok(self.transition(ModeState::Action, timestamp));
                }
            }
            ModeState::SafeExit => {
                if elapsed >= self.config.timeouts.safe_exit_lock && recovered {
                    return Ok(self.transition(ModeState::Rest, timestamp));
                }
            }
        }

        Ok(self.state)
    }

    fn transition(&mut self, new_state: ModeState, timestamp: f64) -> ModeState {
        if new_state != self.state {
            self.state = new_state;
            self.state_entered_at = Some(timestamp);
        }
        self.last_timestamp = Some(timestamp);
        self.state
    }

    fn transition_to_safe_exit(&mut self, timestamp: f64) -> ModeState {
        if self.config.delays.protective_to_safe_exit < 0.0 {
            panic!("Delay budget cannot be negative");
        }
        self.transition(ModeState::SafeExit, timestamp)
    }

    fn validate_timestamp(&mut self, timestamp: f64) -> Result<(), &'static str> {
        if let Some(last) = self.last_timestamp {
            if timestamp < last {
                return Err("timestamp regression");
            }
        }
        self.last_timestamp = Some(timestamp);
        Ok(())
    }

    fn any_guard<F>(&self, metrics: MetricsSnapshot, guards: GuardConfig, predicate: F) -> bool
    where
        F: Fn(GuardBand, f64) -> bool,
    {
        predicate(guards.kappa, metrics.kappa)
            || predicate(guards.var, metrics.var)
            || predicate(guards.max_drawdown, metrics.max_drawdown)
            || predicate(guards.heat, metrics.heat)
    }

    fn all_guard<F>(&self, metrics: MetricsSnapshot, guards: GuardConfig, predicate: F) -> bool
    where
        F: Fn(GuardBand, f64) -> bool,
    {
        predicate(guards.kappa, metrics.kappa)
            && predicate(guards.var, metrics.var)
            && predicate(guards.max_drawdown, metrics.max_drawdown)
            && predicate(guards.heat, metrics.heat)
    }
}

