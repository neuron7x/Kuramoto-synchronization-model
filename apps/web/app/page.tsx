'use client'

import type { ChangeEvent } from 'react'
import { useMemo, useState } from 'react'

import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import CardHeader from '@mui/material/CardHeader'
import Chip from '@mui/material/Chip'
import Container from '@mui/material/Container'
import Grid from '@mui/material/Grid'
import LinearProgress from '@mui/material/LinearProgress'
import List from '@mui/material/List'
import ListItem from '@mui/material/ListItem'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'

import AssignmentIcon from '@mui/icons-material/Assignment'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DownloadIcon from '@mui/icons-material/Download'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'

type ScenarioField = 'initialBalance' | 'riskPerTrade' | 'maxPositions' | 'timeframe'

type ScenarioConfig = {
  initialBalance: number
  riskPerTrade: number
  maxPositions: number
  timeframe: string
}

type ScenarioDraft = Record<ScenarioField, string>

type ScenarioTemplate = {
  id: string
  label: string
  description: string
  defaults: ScenarioConfig
  notes: string[]
}

type FieldMeta = {
  label: string
  helper: string
  placeholder: string
  inputMode?: 'decimal' | 'numeric' | 'text'
  type?: 'number' | 'text'
}

type ScenarioHealthStatus = 'Production-ready' | 'Needs review' | 'High risk' | 'Resolve errors'

type ScenarioHealth = {
  status: ScenarioHealthStatus
  score: number
  summary: string
  checklist: string[]
}

const HEALTH_STATUS_CONFIG: Record<ScenarioHealthStatus, { color: 'success' | 'warning' | 'error'; Icon: typeof CheckCircleIcon }> =
  {
    'Production-ready': {
      color: 'success',
      Icon: CheckCircleIcon,
    },
    'Needs review': {
      color: 'warning',
      Icon: WarningAmberIcon,
    },
    'High risk': {
      color: 'error',
      Icon: ErrorOutlineIcon,
    },
    'Resolve errors': {
      color: 'error',
      Icon: ErrorOutlineIcon,
    },
  }

const FIELD_META: Record<ScenarioField, FieldMeta> = {
  initialBalance: {
    label: 'Initial balance (USD)',
    helper: 'Recommended: ≥ 1,000 USD to produce stable Monte Carlo paths.',
    placeholder: '10000',
    inputMode: 'decimal',
    type: 'number',
  },
  riskPerTrade: {
    label: 'Risk per trade (%)',
    helper: 'Keep between 0.25% and 2% for resilient drawdown control.',
    placeholder: '1',
    inputMode: 'decimal',
    type: 'number',
  },
  maxPositions: {
    label: 'Max concurrent positions',
    helper: 'Use a small integer (1-5) unless you have portfolio hedging.',
    placeholder: '3',
    inputMode: 'numeric',
    type: 'number',
  },
  timeframe: {
    label: 'Execution timeframe',
    helper: 'Format: <number><unit> with unit in s, m, h, d, w (e.g. 1h).',
    placeholder: '1h',
  },
}

const SCENARIO_TEMPLATES: ScenarioTemplate[] = [
  {
    id: 'momentum-breakout',
    label: 'Momentum Breakout',
    description: 'Targets high volume breakouts with moderate exposure.',
    defaults: {
      initialBalance: 15000,
      riskPerTrade: 1,
      maxPositions: 3,
      timeframe: '1h',
    },
    notes: [
      'Requires fast data refresh (≤ 1 minute).',
      'Pair with trailing stops to lock in momentum exhaustion.',
    ],
  },
  {
    id: 'mean-reversion',
    label: 'Mean Reversion Swing',
    description: 'Aims to fade extended moves with conservative sizing.',
    defaults: {
      initialBalance: 10000,
      riskPerTrade: 0.5,
      maxPositions: 2,
      timeframe: '4h',
    },
    notes: [
      'Ensure data set spans multiple regimes to avoid biased reversion.',
      'Layer with volatility filters to avoid trending environments.',
    ],
  },
  {
    id: 'volatility-breakout',
    label: 'Volatility Expansion',
    description: 'Captures volatility squeezes with disciplined portfolio caps.',
    defaults: {
      initialBalance: 25000,
      riskPerTrade: 0.75,
      maxPositions: 4,
      timeframe: '30m',
    },
    notes: [
      'Backtest with intraday transaction costs and slippage.',
      'Consider volatility-adjusted position sizing for calmer sessions.',
    ],
  },
]

type FieldErrors = Record<ScenarioField, string | null>

function parseNumber(value: string): number {
  const trimmed = value.replace(/,/g, '').trim()
  if (!trimmed) {
    return Number.NaN
  }
  return Number(trimmed)
}

function toDraft(config: ScenarioConfig): ScenarioDraft {
  return {
    initialBalance: config.initialBalance.toString(),
    riskPerTrade: config.riskPerTrade.toString(),
    maxPositions: config.maxPositions.toString(),
    timeframe: config.timeframe,
  }
}

function parseDraft(draft: ScenarioDraft): ScenarioConfig {
  const initialBalance = parseNumber(draft.initialBalance)
  const riskPerTrade = parseNumber(draft.riskPerTrade)
  const maxPositions = parseNumber(draft.maxPositions)
  return {
    initialBalance,
    riskPerTrade,
    maxPositions: Number.isFinite(maxPositions) ? Math.trunc(maxPositions) : Number.NaN,
    timeframe: draft.timeframe.trim(),
  }
}

function validateDraft(draft: ScenarioDraft): FieldErrors {
  const parsed = parseDraft(draft)
  const errors: FieldErrors = {
    initialBalance: null,
    riskPerTrade: null,
    maxPositions: null,
    timeframe: null,
  }

  if (!Number.isFinite(parsed.initialBalance) || parsed.initialBalance <= 0) {
    errors.initialBalance = 'Enter a positive starting balance. Include only digits (no currency symbols).'
  } else if (parsed.initialBalance < 500) {
    errors.initialBalance = 'Balances under 500 USD often create unstable allocations. Consider at least 500+.'
  }

  if (!Number.isFinite(parsed.riskPerTrade) || parsed.riskPerTrade <= 0) {
    errors.riskPerTrade = 'Risk per trade must be a positive percentage (e.g. 0.5 for 0.5%).'
  } else if (parsed.riskPerTrade > 5) {
    errors.riskPerTrade = 'Risk above 5% is rarely survivable. Reduce exposure or split the position.'
  }

  if (!Number.isFinite(parsed.maxPositions) || parsed.maxPositions <= 0) {
    errors.maxPositions = 'Set how many concurrent positions you allow. Use an integer greater than zero.'
  } else if (parsed.maxPositions > 10) {
    errors.maxPositions = 'Managing more than 10 simultaneous trades is error-prone. Tighten the cap.'
  }

  if (!parsed.timeframe) {
    errors.timeframe = 'Provide a timeframe such as 1m, 30m, 1h or 1d.'
  } else if (!/^\d+(s|m|h|d|w)$/i.test(parsed.timeframe)) {
    errors.timeframe = 'Timeframe must match <number><unit> (units: s, m, h, d, w). Example: 4h.'
  }

  return errors
}

function computeWarnings(config: ScenarioConfig): string[] {
  const warnings: string[] = []
  const { initialBalance, riskPerTrade, maxPositions } = config

  if (Number.isFinite(initialBalance) && Number.isFinite(riskPerTrade) && initialBalance > 0) {
    const riskDollars = (initialBalance * riskPerTrade) / 100
    if (riskDollars > initialBalance * 0.03) {
      warnings.push(
        `Each position risks $${riskDollars.toFixed(2)}, which exceeds 3% of equity. Consider reducing risk per trade.`,
      )
    } else if (riskDollars < initialBalance * 0.001) {
      warnings.push(
        `Each position risks only $${riskDollars.toFixed(2)}. Verify commissions do not dominate P&L.`,
      )
    }

    if (Number.isFinite(maxPositions) && maxPositions > 0) {
      const portfolioAtRisk = riskDollars * maxPositions
      if (portfolioAtRisk > initialBalance * 0.2) {
        warnings.push(
          `Simultaneous risk is $${portfolioAtRisk.toFixed(2)} (~${((portfolioAtRisk / initialBalance) * 100).toFixed(
            1,
          )}% of equity). Add position staggering or tighten limits.`,
        )
      }
    }
  }

  return warnings
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function convertTimeframeToMinutes(timeframe: string): number | null {
  const match = timeframe.match(/^(\d+)([smhdw])$/i)
  if (!match) {
    return null
  }
  const amount = Number(match[1])
  const unit = match[2].toLowerCase()
  if (!Number.isFinite(amount) || amount <= 0) {
    return null
  }
  const multipliers: Record<string, number> = {
    s: 1 / 60,
    m: 1,
    h: 60,
    d: 1440,
    w: 10080,
  }
  const multiplier = multipliers[unit]
  if (multiplier === undefined) {
    return null
  }
  return amount * multiplier
}

function describeTimeframe(timeframe: string): string | null {
  const match = timeframe.match(/^(\d+)([smhdw])$/i)
  if (!match) {
    return null
  }
  const amount = Number(match[1])
  if (!Number.isFinite(amount)) {
    return null
  }
  const unit = match[2].toLowerCase()
  const labels: Record<string, string> = {
    s: 'second',
    m: 'minute',
    h: 'hour',
    d: 'day',
    w: 'week',
  }
  const label = labels[unit]
  if (!label) {
    return null
  }
  return `${amount} ${amount === 1 ? label : `${label}s`}`
}

function buildTimeframeInsights(timeframe: string): string[] {
  const minutes = convertTimeframeToMinutes(timeframe)
  if (minutes === null) {
    return []
  }
  const insights: string[] = []
  const description = describeTimeframe(timeframe)
  if (description) {
    insights.push(`Expect data refresh at least every ${description} to keep signals aligned.`)
  }
  if (minutes > 0) {
    const barsPerDay = Math.round((24 * 60) / minutes)
    if (barsPerDay >= 1200) {
      insights.push('Expect well over 1,200 bars per day—ensure streaming analytics and log aggregation are in place.')
    } else if (barsPerDay > 0) {
      insights.push(`Roughly ${barsPerDay.toLocaleString()} bars per day—size Monte Carlo samples accordingly.`)
    }
  }
  if (minutes <= 5) {
    insights.push('Execution cadence is fast; confirm order routing and slippage controls are tuned for low latency.')
  } else if (minutes <= 60) {
    insights.push('Mid-frequency cadence allows session-based monitoring. Prepare intraday review checklists.')
  } else if (minutes >= 720 && minutes < 1440) {
    insights.push('Plan for daily risk syncs—the cadence spans multiple sessions, so overnight gaps matter.')
  } else if (minutes >= 1440) {
    insights.push('Slow cadence—capture macro or fundamental catalysts between bars to avoid stale positioning.')
  }
  return insights
}

function evaluateScenario(
  config: ScenarioConfig,
  warnings: string[],
  hasErrors: boolean,
): ScenarioHealth {
  const checklist: string[] = []

  if (hasErrors) {
    checklist.push('Resolve the highlighted fields above to calculate a deployable scenario.')
    if (warnings.length > 0) {
      checklist.push('Revisit the risk warnings once validation errors are cleared.')
    }
    return {
      status: 'Resolve errors',
      score: 25,
      summary: 'Fix validation errors to unlock export actions and a reliable health score.',
      checklist,
    }
  }

  const { initialBalance, riskPerTrade, maxPositions, timeframe } = config

  if (
    !Number.isFinite(initialBalance) ||
    !Number.isFinite(riskPerTrade) ||
    !Number.isFinite(maxPositions) ||
    !timeframe
  ) {
    checklist.push('Populate every input so health checks can benchmark risk exposure.')
    return {
      status: 'Needs review',
      score: 45,
      summary: 'Complete the remaining fields to benchmark the scenario and surface optimisation ideas.',
      checklist,
    }
  }

  let score = 95

  if (warnings.length > 0) {
    score -= Math.min(45, warnings.length * 12)
    checklist.push('Address the risk snapshot warnings to tighten the scenario envelope.')
  }

  if (initialBalance < 5000) {
    score -= 12
    checklist.push('Increase the initial balance towards ≥ 5k to stabilise Monte Carlo paths.')
  }

  if (riskPerTrade > 2) {
    score -= 10
    checklist.push('Keep risk per trade at or below 2% to stay within resilient drawdown tolerances.')
  } else if (riskPerTrade < 0.25) {
    score -= 6
    checklist.push('Confirm commissions remain negligible when risking under 0.25% per trade.')
  }

  if (maxPositions > 6) {
    score -= 8
    checklist.push('Limit concurrent positions to ≤ 6 unless execution is heavily automated.')
  }

  const riskDollars = (initialBalance * riskPerTrade) / 100
  const portfolioRisk = riskDollars * maxPositions
  if (portfolioRisk > initialBalance * 0.25) {
    score -= 10
    checklist.push('Trim portfolio risk below 25% of equity to avoid cascading losses.')
  }

  const minutes = convertTimeframeToMinutes(timeframe)
  if (minutes !== null) {
    if (minutes <= 5) {
      score -= 6
      checklist.push('Verify data infrastructure supports sub-five-minute execution cadence.')
    } else if (minutes >= 720) {
      checklist.push('Document overnight gap handling for higher timeframe execution.')
    }
  }

  const boundedScore = Math.round(clamp(score, 20, 100))

  let status: ScenarioHealthStatus
  let summary: string
  if (boundedScore >= 80) {
    status = 'Production-ready'
    summary = 'Risk controls look balanced. Document execution assumptions before promotion.'
  } else if (boundedScore >= 55) {
    status = 'Needs review'
    summary = 'Scenario is workable but tighten the highlighted levers before automation.'
  } else {
    status = 'High risk'
    summary = 'Risk envelope is stretched. Reduce concentration before running the strategy in staging.'
  }

  const uniqueChecklist = Array.from(new Set(checklist))

  return {
    status,
    score: boundedScore,
    summary,
    checklist: uniqueChecklist,
  }
}

export default function Home() {
  const [templateId, setTemplateId] = useState<string>(SCENARIO_TEMPLATES[0].id)
  const [draft, setDraft] = useState<ScenarioDraft>(() => toDraft(SCENARIO_TEMPLATES[0].defaults))
  const [actionMessage, setActionMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)

  const selectedTemplate = useMemo(
    () => SCENARIO_TEMPLATES.find((entry) => entry.id === templateId) ?? SCENARIO_TEMPLATES[0],
    [templateId],
  )

  const parsedConfig = useMemo(() => parseDraft(draft), [draft])
  const errors = useMemo(() => validateDraft(draft), [draft])
  const hasErrors = useMemo(() => Object.values(errors).some((item) => item !== null), [errors])
  const warnings = useMemo(() => computeWarnings(parsedConfig), [parsedConfig])
  const preview = useMemo(() => JSON.stringify(buildPreview(parsedConfig), null, 2), [parsedConfig])
  const timeframeInsights = useMemo(() => buildTimeframeInsights(parsedConfig.timeframe), [parsedConfig.timeframe])
  const scenarioHealth = useMemo(() => evaluateScenario(parsedConfig, warnings, hasErrors), [parsedConfig, warnings, hasErrors])

  const riskDollars = useMemo(() => {
    if (!Number.isFinite(parsedConfig.initialBalance) || !Number.isFinite(parsedConfig.riskPerTrade)) {
      return null
    }
    return (parsedConfig.initialBalance * parsedConfig.riskPerTrade) / 100
  }, [parsedConfig])

  const aggregateRisk = useMemo(() => {
    if (riskDollars === null || !Number.isFinite(parsedConfig.maxPositions)) {
      return null
    }
    return riskDollars * parsedConfig.maxPositions
  }, [parsedConfig, riskDollars])

  const riskPercentOfEquity = useMemo(() => {
    if (
      riskDollars === null ||
      !Number.isFinite(parsedConfig.initialBalance) ||
      parsedConfig.initialBalance === 0
    ) {
      return null
    }
    return (riskDollars / parsedConfig.initialBalance) * 100
  }, [parsedConfig, riskDollars])

  const portfolioRiskPercent = useMemo(() => {
    if (
      aggregateRisk === null ||
      !Number.isFinite(parsedConfig.initialBalance) ||
      parsedConfig.initialBalance === 0
    ) {
      return null
    }
    return (aggregateRisk / parsedConfig.initialBalance) * 100
  }, [aggregateRisk, parsedConfig])

  const handleChange = (field: ScenarioField) => (
    event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    const value = event.target.value
    setActionMessage(null)
    setDraft((current) => ({ ...current, [field]: value }))
  }

  const resetTemplate = () => {
    setDraft(toDraft(selectedTemplate.defaults))
    setActionMessage(null)
  }

  const handleCopy = async () => {
    if (hasErrors) {
      setActionMessage({
        kind: 'error',
        text: 'Resolve form errors before exporting the scenario JSON.',
      })
      return
    }

    try {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
        throw new Error('Clipboard API unavailable')
      }
      await navigator.clipboard.writeText(preview)
      setActionMessage({ kind: 'success', text: 'Scenario JSON copied to clipboard.' })
    } catch (error) {
      setActionMessage({
        kind: 'error',
        text: 'Failed to copy the scenario JSON. Please try again.',
      })
    }
  }

  const handleDownload = () => {
    if (hasErrors) {
      setActionMessage({
        kind: 'error',
        text: 'Resolve form errors before exporting the scenario JSON.',
      })
      return
    }

    try {
      const blob = new Blob([preview], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `scenario-${templateId}.json`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setActionMessage({ kind: 'success', text: 'Scenario JSON download started.' })
    } catch (error) {
      setActionMessage({
        kind: 'error',
        text: 'Failed to start the scenario JSON download. Please try again.',
      })
    }
  }

  const templateHelperId = 'template-description'
  const statusVisual = HEALTH_STATUS_CONFIG[scenarioHealth.status]
  const StatusIcon = statusVisual.Icon
  const statusChipColor = statusVisual.color

  return (
    <Box
      component="main"
      data-testid="scenario-main"
      sx={{ minHeight: '100vh', py: { xs: 4, md: 6 } }}
    >
      <Container maxWidth="xl" data-testid="scenario-container">
        <Stack spacing={{ xs: 5, md: 6 }}>
          <Stack spacing={1.5} data-testid="onboarding-hero">
            <Typography variant="h3" component="h1">
              Scenario Studio
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Sanity-check strategy inputs before pushing them into execution. Select a template, adjust the levers, and review
              automatic hints about risk concentration and timeframe hygiene.
            </Typography>
          </Stack>

          <Grid container spacing={4}>
            <Grid item xs={12} lg={7}>
              <Card component="section" variant="outlined" data-testid="scenario-template-panel">
                <CardHeader
                  title="Strategy configuration"
                  subheader="Choose a template, calibrate risk settings, and export a JSON blueprint when validation passes."
                />
                <CardContent>
                  <Stack spacing={4}>
                    <Box data-testid="template-selector">
                      <TextField
                        select
                        fullWidth
                        id="template"
                        label="Scenario template"
                        value={templateId}
                        onChange={(event) => {
                          const value = event.target.value
                          setTemplateId(value)
                          setActionMessage(null)
                          const template = SCENARIO_TEMPLATES.find((entry) => entry.id === value)
                          if (template) {
                            setDraft(toDraft(template.defaults))
                          }
                        }}
                        SelectProps={{ native: true }}
                        inputProps={{
                          'data-testid': 'template-select',
                          'aria-describedby': templateHelperId,
                        }}
                      >
                        {SCENARIO_TEMPLATES.map((template) => (
                          <option key={template.id} value={template.id}>
                            {template.label}
                          </option>
                        ))}
                      </TextField>

                      <Typography
                        variant="body2"
                        color="text.secondary"
                        id={templateHelperId}
                        data-testid="template-description"
                        sx={{ mt: 1.5 }}
                      >
                        {selectedTemplate.description}
                      </Typography>

                      <List dense disablePadding data-testid="template-notes" sx={{ mt: 2, pl: 0 }}>
                        {selectedTemplate.notes.map((note) => (
                          <ListItem key={note} disableGutters sx={{ alignItems: 'flex-start', py: 0.5 }}>
                            <ListItemIcon sx={{ minWidth: 32, mt: '3px' }}>
                              <AssignmentIcon color="primary" fontSize="small" />
                            </ListItemIcon>
                            <ListItemText
                              primary={note}
                              primaryTypographyProps={{ variant: 'body2', color: 'text.secondary' }}
                            />
                          </ListItem>
                        ))}
                      </List>
                    </Box>

                    <Box component="form" noValidate data-testid="scenario-form">
                      <Grid container spacing={3}>
                        {(Object.keys(FIELD_META) as ScenarioField[]).map((field) => {
                          const meta = FIELD_META[field]
                          const inputId = `field-${field}`
                          const helperId = `${inputId}-helper`
                          const errorId = `${inputId}-error`
                          const hasError = Boolean(errors[field])
                          const describedBy = hasError ? `${helperId} ${errorId}` : helperId

                          return (
                            <Grid item xs={12} sm={6} data-testid={`field-${field}`} key={field}>
                              <Stack spacing={1}>
                                <TextField
                                  fullWidth
                                  id={inputId}
                                  name={field}
                                  label={meta.label}
                                  value={draft[field]}
                                  onChange={handleChange(field)}
                                  placeholder={meta.placeholder}
                                  type={meta.type}
                                  error={hasError}
                                  helperText={meta.helper}
                                  FormHelperTextProps={{
                                    id: helperId,
                                  }}
                                  inputProps={{
                                    inputMode: meta.inputMode,
                                    'data-testid': `input-${field}`,
                                    'aria-describedby': describedBy,
                                    step: meta.type === 'number' ? 'any' : undefined,
                                  }}
                                  autoComplete="off"
                                />
                                {hasError ? (
                                  <Typography
                                    variant="body2"
                                    color="error"
                                    id={errorId}
                                    data-testid={`error-${field}`}
                                  >
                                    {errors[field]}
                                  </Typography>
                                ) : null}
                              </Stack>
                            </Grid>
                          )
                        })}
                      </Grid>

                      <Stack
                        direction={{ xs: 'column', sm: 'row' }}
                        spacing={1.5}
                        justifyContent={{ xs: 'stretch', sm: 'flex-end' }}
                        alignItems={{ xs: 'stretch', sm: 'center' }}
                        sx={{ mt: 4 }}
                        data-testid="action-buttons"
                      >
                        <Button
                          type="button"
                          variant="outlined"
                          color="inherit"
                          onClick={resetTemplate}
                          startIcon={<RestartAltIcon />}
                          data-testid="action-reset"
                        >
                          Reset to template defaults
                        </Button>
                        <Button
                          type="button"
                          variant="contained"
                          color="primary"
                          onClick={handleCopy}
                          disabled={hasErrors}
                          startIcon={<ContentCopyIcon />}
                          data-testid="action-copy"
                        >
                          Copy to clipboard
                        </Button>
                        <Button
                          type="button"
                          variant="contained"
                          color="secondary"
                          onClick={handleDownload}
                          disabled={hasErrors}
                          startIcon={<DownloadIcon />}
                          data-testid="action-download"
                        >
                          Download JSON
                        </Button>
                      </Stack>

                      {actionMessage ? (
                        <Alert
                          severity={actionMessage.kind === 'success' ? 'success' : 'error'}
                          role="status"
                          aria-live="polite"
                          data-testid="action-feedback"
                          sx={{ mt: 3 }}
                        >
                          {actionMessage.text}
                        </Alert>
                      ) : null}
                    </Box>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} lg={5}>
              <Stack spacing={3} data-testid="insights-panels">
                <Card component="article" variant="outlined" data-testid="scenario-health">
                  <CardHeader title="Scenario health" />
                  <CardContent>
                    <Stack spacing={2}>
                      <Box data-testid="health-status">
                        <Chip
                          icon={<StatusIcon fontSize="small" />}
                          label={scenarioHealth.status}
                          color={statusChipColor}
                          variant="filled"
                          sx={{ fontSize: '0.95rem', px: 1.5, py: 0.5 }}
                        />
                      </Box>

                      <Typography variant="body1" fontWeight={600} data-testid="health-score">
                        Score: {scenarioHealth.score} / 100
                      </Typography>

                      <Box
                        role="meter"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={scenarioHealth.score}
                        aria-valuetext={`${scenarioHealth.score} out of 100`}
                        data-testid="health-meter"
                        sx={{ mt: -0.5 }}
                      >
                        <LinearProgress
                          variant="determinate"
                          value={scenarioHealth.score}
                          color={statusChipColor}
                          sx={{ height: 10, borderRadius: 999 }}
                        />
                      </Box>

                      <Typography variant="body1" color="text.secondary" data-testid="health-summary">
                        {scenarioHealth.summary}
                      </Typography>

                      {scenarioHealth.checklist.length > 0 ? (
                        <List dense disablePadding data-testid="health-checklist">
                          {scenarioHealth.checklist.map((item) => (
                            <ListItem key={item} disableGutters sx={{ alignItems: 'flex-start', py: 0.5 }}>
                              <ListItemIcon sx={{ minWidth: 32, mt: '3px' }}>
                                <CheckCircleIcon color="primary" fontSize="small" />
                              </ListItemIcon>
                              <ListItemText
                                primary={item}
                                primaryTypographyProps={{ variant: 'body2', color: 'text.secondary' }}
                              />
                            </ListItem>
                          ))}
                        </List>
                      ) : null}
                    </Stack>
                  </CardContent>
                </Card>

                <Card component="article" variant="outlined" data-testid="risk-snapshot">
                  <CardHeader title="Risk snapshot" />
                  <CardContent>
                    <Stack spacing={3} data-testid="metric-grid">
                      <Grid container spacing={2}>
                        <Grid item xs={12} sm={4}>
                          <Paper variant="outlined" data-testid="metric-risk-per-trade" sx={{ p: 2, borderRadius: 3 }}>
                            <Typography variant="subtitle2" color="text.secondary">
                              Risk per trade
                            </Typography>
                            <Typography variant="h6">
                              {riskDollars === null ? '—' : `$${riskDollars.toFixed(2)}`}
                            </Typography>
                            {riskPercentOfEquity !== null ? (
                              <Typography variant="body2" color="text.secondary">
                                {riskPercentOfEquity.toFixed(2)}% of equity
                              </Typography>
                            ) : null}
                          </Paper>
                        </Grid>
                        <Grid item xs={12} sm={4}>
                          <Paper variant="outlined" data-testid="metric-portfolio-risk" sx={{ p: 2, borderRadius: 3 }}>
                            <Typography variant="subtitle2" color="text.secondary">
                              Max portfolio risk
                            </Typography>
                            <Typography variant="h6">
                              {aggregateRisk === null ? '—' : `$${aggregateRisk.toFixed(2)}`}
                            </Typography>
                            {portfolioRiskPercent !== null ? (
                              <Typography variant="body2" color="text.secondary">
                                {portfolioRiskPercent.toFixed(2)}% of equity
                              </Typography>
                            ) : null}
                          </Paper>
                        </Grid>
                        <Grid item xs={12} sm={4}>
                          <Paper variant="outlined" data-testid="metric-timeframe" sx={{ p: 2, borderRadius: 3 }}>
                            <Typography variant="subtitle2" color="text.secondary">
                              Timeframe
                            </Typography>
                            <Typography variant="h6">{parsedConfig.timeframe || '—'}</Typography>
                          </Paper>
                        </Grid>
                      </Grid>

                      {warnings.length > 0 ? (
                        <Stack spacing={1.5} data-testid="warning-list">
                          {warnings.map((warning) => (
                            <Alert
                              key={warning}
                              severity="warning"
                              icon={<WarningAmberIcon />}
                              sx={{ alignItems: 'flex-start' }}
                            >
                              {warning}
                            </Alert>
                          ))}
                        </Stack>
                      ) : (
                        <Typography color="text.secondary" data-testid="warning-placeholder">
                          Risk controls look balanced for the selected template. Stress test transaction costs before live execution.
                        </Typography>
                      )}

                      {hasErrors ? (
                        <Alert severity="error" data-testid="error-export-blocker">
                          Resolve the highlighted fields above to unlock export-ready scenario JSON.
                        </Alert>
                      ) : null}

                      {timeframeInsights.length > 0 ? (
                        <Paper variant="outlined" data-testid="timeframe-insights" sx={{ p: 2.5, borderRadius: 3 }}>
                          <Typography variant="h6" sx={{ mb: 1 }}>
                            Timeframe insights
                          </Typography>
                          <List dense disablePadding>
                            {timeframeInsights.map((insight) => (
                              <ListItem key={insight} disableGutters sx={{ py: 0.5 }}>
                                <ListItemIcon sx={{ minWidth: 32, mt: '3px' }}>
                                  <AssignmentIcon color="primary" fontSize="small" />
                                </ListItemIcon>
                                <ListItemText
                                  primary={insight}
                                  primaryTypographyProps={{ variant: 'body2', color: 'text.secondary' }}
                                />
                              </ListItem>
                            ))}
                          </List>
                        </Paper>
                      ) : null}
                    </Stack>
                  </CardContent>
                </Card>

                <Card component="article" variant="outlined" data-testid="scenario-preview">
                  <CardHeader title="Scenario JSON template" />
                  <CardContent>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      Drop this snippet into <code>docs/scenarios.md</code> or configuration files as a starting point for backtests.
                    </Typography>
                    <Box
                      component="pre"
                      data-testid="scenario-json-preview"
                      aria-label="Scenario JSON preview"
                      sx={{
                        bgcolor: '#0f172a',
                        color: '#e2e8f0',
                        borderRadius: 3,
                        p: 2.5,
                        fontSize: 14,
                        overflowX: 'auto',
                        boxShadow: 'inset 0 0 0 1px rgba(148, 163, 184, 0.2)',
                      }}
                    >
                      {preview}
                    </Box>
                  </CardContent>
                </Card>
              </Stack>
            </Grid>
          </Grid>
        </Stack>
      </Container>
    </Box>
  )
}

function buildPreview(config: ScenarioConfig) {
  return {
    initialBalance: Number.isFinite(config.initialBalance) ? Number(config.initialBalance.toFixed(2)) : null,
    riskPerTrade: Number.isFinite(config.riskPerTrade) ? Number(config.riskPerTrade.toFixed(2)) : null,
    maxPositions: Number.isFinite(config.maxPositions) ? config.maxPositions : null,
    timeframe: config.timeframe || null,
  }
}
