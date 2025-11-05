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
import type { TextFieldProps } from '@mui/material/TextField'
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

const HEALTH_STATUS_CONFIG: Record<
  ScenarioHealthStatus,
  { color: 'success' | 'warning' | 'error'; Icon: typeof CheckCircleIcon }
> = {
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

type HelperTextSlotProps = NonNullable<TextFieldProps['slotProps']>['formHelperText']

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
    errors.initialBalance =
      'Enter a positive starting balance. Include only digits (no currency symbols).'
  } else if (parsed.initialBalance < 500) {
    errors.initialBalance =
      'Balances under 500 USD often create unstable allocations. Consider at least 500+.'
  }

  if (!Number.isFinite(parsed.riskPerTrade) || parsed.riskPerTrade <= 0) {
    errors.riskPerTrade = 'Risk per trade must be a positive percentage (e.g. 0.5 for 0.5%).'
  } else if (parsed.riskPerTrade > 5) {
    errors.riskPerTrade =
      'Risk above 5% is rarely survivable. Reduce exposure or split the position.'
  }

  if (!Number.isFinite(parsed.maxPositions) || parsed.maxPositions <= 0) {
    errors.maxPositions =
      'Set how many concurrent positions you allow. Use an integer greater than zero.'
  } else if (parsed.maxPositions > 10) {
    errors.maxPositions =
      'Managing more than 10 simultaneous trades is error-prone. Tighten the cap.'
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
        `Each position risks $${riskDollars.toFixed(2)}, which exceeds 3% of equity. Consider reducing risk per trade.`
      )
    } else if (riskDollars < initialBalance * 0.001) {
      warnings.push(
        `Each position risks only $${riskDollars.toFixed(2)}. Verify commissions do not dominate P&L.`
      )
    }

    if (Number.isFinite(maxPositions) && maxPositions > 0) {
      const portfolioAtRisk = riskDollars * maxPositions
      if (portfolioAtRisk > initialBalance * 0.2) {
        warnings.push(
          `Simultaneous risk is $${portfolioAtRisk.toFixed(2)} (~${((portfolioAtRisk / initialBalance) * 100).toFixed(1)}% of equity). Add position staggering or tighten limits.`
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
      insights.push(
        'Expect well over 1,200 bars per day—ensure streaming analytics and log aggregation are in place.'
      )
    } else if (barsPerDay > 0) {
      insights.push(
        `Roughly ${barsPerDay.toLocaleString()} bars per day—size Monte Carlo samples accordingly.`
      )
    }
  }
  if (minutes <= 5) {
    insights.push(
      'Execution cadence is fast; confirm order routing and slippage controls are tuned for low latency.'
    )
  } else if (minutes <= 60) {
    insights.push(
      'Mid-frequency cadence allows session-based monitoring. Prepare intraday review checklists.'
    )
  } else if (minutes >= 720 && minutes < 1440) {
    insights.push(
      'Plan for daily risk syncs—the cadence spans multiple sessions, so overnight gaps matter.'
    )
  } else if (minutes >= 1440) {
    insights.push(
      'Slow cadence—capture macro or fundamental catalysts between bars to avoid stale positioning.'
    )
  }
  return insights
}

function evaluateScenario(
  config: ScenarioConfig,
  warnings: string[],
  hasErrors: boolean
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
      summary:
        'Complete the remaining fields to benchmark the scenario and surface optimisation ideas.',
      checklist,
    }
  }

  let score = 95

  if (warnings.length > 0) {
    score -= Math.min(60, warnings.length * 15)
    checklist.push('Address the risk snapshot warnings to tighten the scenario envelope.')
  }

  if (initialBalance < 5000) {
    score -= 12
    checklist.push('Increase the initial balance towards ≥ 5k to stabilise Monte Carlo paths.')
  }

  if (riskPerTrade > 2) {
    score -= 10
    checklist.push(
      'Keep risk per trade at or below 2% to stay within resilient drawdown tolerances.'
    )
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
    summary =
      'Risk envelope is stretched. Reduce concentration before running the strategy in staging.'
  }

  const uniqueChecklist = Array.from(new Set(checklist))

  return {
    status,
    score: boundedScore,
    summary,
    checklist: uniqueChecklist,
  }
}

type ActionMessage = {
  kind: 'success' | 'error'
  text: string
} | null

type FieldKey = keyof typeof FIELD_META

export function ScenarioStudio() {
  const [templateId, setTemplateId] = useState<string>(SCENARIO_TEMPLATES[0]?.id ?? '')
  const [draft, setDraft] = useState<ScenarioDraft>(() =>
    SCENARIO_TEMPLATES[0]
      ? toDraft(SCENARIO_TEMPLATES[0].defaults)
      : toDraft({
          initialBalance: 0,
          riskPerTrade: 0,
          maxPositions: 0,
          timeframe: '',
        })
  )
  const [actionMessage, setActionMessage] = useState<ActionMessage>(null)

  const selectedTemplate = useMemo(() => {
    return (
      SCENARIO_TEMPLATES.find((template) => template.id === templateId) ?? SCENARIO_TEMPLATES[0]
    )
  }, [templateId])

  const handleFieldChange = (field: FieldKey) => (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value
    setDraft((previous) => ({ ...previous, [field]: value }))
    setActionMessage(null)
  }

  const parsedConfig = useMemo(() => parseDraft(draft), [draft])
  const errors = useMemo(() => validateDraft(draft), [draft])
  const hasErrors = useMemo(() => Object.values(errors).some((value) => value !== null), [errors])
  const warnings = useMemo(() => computeWarnings(parsedConfig), [parsedConfig])
  const timeframeInsights = useMemo(
    () => buildTimeframeInsights(parsedConfig.timeframe),
    [parsedConfig.timeframe]
  )
  const scenarioHealth = useMemo(
    () => evaluateScenario(parsedConfig, warnings, hasErrors),
    [parsedConfig, warnings, hasErrors]
  )

  const preview = useMemo(() => {
    if (hasErrors || !selectedTemplate) {
      return '{\n  "error": "Resolve validation issues before exporting the scenario."\n}'
    }

    const normalized: ScenarioConfig = {
      initialBalance: Number.isFinite(parsedConfig.initialBalance)
        ? parsedConfig.initialBalance
        : 0,
      riskPerTrade: Number.isFinite(parsedConfig.riskPerTrade) ? parsedConfig.riskPerTrade : 0,
      maxPositions: Number.isFinite(parsedConfig.maxPositions) ? parsedConfig.maxPositions : 0,
      timeframe: parsedConfig.timeframe,
    }

    const payload = {
      template: templateId,
      configuration: {
        initialBalance: Number.isFinite(normalized.initialBalance)
          ? Number(normalized.initialBalance)
          : normalized.initialBalance,
        riskPerTradePercent: Number.isFinite(normalized.riskPerTrade)
          ? Number(normalized.riskPerTrade)
          : normalized.riskPerTrade,
        maxConcurrentPositions: normalized.maxPositions,
        timeframe: normalized.timeframe,
      },
      health: {
        score: scenarioHealth.score,
        status: scenarioHealth.status,
        warnings,
      },
    }

    return JSON.stringify(payload, null, 2)
  }, [
    hasErrors,
    parsedConfig,
    scenarioHealth.score,
    scenarioHealth.status,
    selectedTemplate,
    templateId,
    warnings,
  ])

  const handleReset = () => {
    if (selectedTemplate) {
      setDraft(toDraft(selectedTemplate.defaults))
      setActionMessage(null)
    }
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
      console.error('Failed to copy scenario JSON', error)
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
      console.error('Failed to download scenario JSON', error)
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
      sx={{
        minHeight: 'calc(100vh - 64px)',
        py: { xs: 3, md: 5 },
        bgcolor: 'background.default',
      }}
    >
      <Container maxWidth="xl" data-testid="scenario-container">
        <Stack spacing={{ xs: 4, md: 5 }}>
          <Stack spacing={2} data-testid="onboarding-hero">
            <Typography variant="h3" component="h1" fontWeight={700}>
              Scenario Studio
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 800 }}>
              Configure and validate trading strategy templates with real-time risk assessment.
              Select a template, adjust parameters, and receive instant feedback on risk
              concentration and operational hygiene before deployment.
            </Typography>
          </Stack>

          <Grid container spacing={{ xs: 3, md: 4 }}>
            <Grid item xs={12} lg={7}>
              <Card
                component="section"
                variant="outlined"
                data-testid="scenario-template-panel"
                sx={{
                  height: '100%',
                  boxShadow: 1,
                  transition: 'box-shadow 0.3s ease',
                  '&:hover': { boxShadow: 3 },
                }}
              >
                <CardHeader
                  title="Strategy Configuration"
                  titleTypographyProps={{ variant: 'h5', fontWeight: 600 }}
                  subheader="Choose a template and configure risk parameters to generate a validated strategy blueprint."
                  subheaderTypographyProps={{ sx: { mt: 0.5 } }}
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
                        {selectedTemplate?.description}
                      </Typography>

                      <List dense disablePadding data-testid="template-notes" sx={{ mt: 2, pl: 0 }}>
                        {selectedTemplate?.notes.map((note) => (
                          <ListItem key={note} sx={{ px: 0 }}>
                            <ListItemIcon sx={{ minWidth: 32 }}>
                              <AssignmentIcon color="primary" fontSize="small" />
                            </ListItemIcon>
                            <ListItemText
                              primary={note}
                              primaryTypographyProps={{ variant: 'body2' }}
                            />
                          </ListItem>
                        ))}
                      </List>
                    </Box>

                    <Grid container spacing={2} data-testid="scenario-form">
                      {(Object.keys(FIELD_META) as FieldKey[]).map((fieldKey) => {
                        const meta = FIELD_META[fieldKey]
                        const error = errors[fieldKey]
                        const fieldTestId = `input-${fieldKey}`
                        const helperTextTestId = error ? `error-${fieldKey}` : undefined
                        return (
                          <Grid key={fieldKey} item xs={12} md={fieldKey === 'timeframe' ? 12 : 6}>
                            <TextField
                              fullWidth
                              id={fieldKey}
                              name={fieldKey}
                              label={meta.label}
                              placeholder={meta.placeholder}
                              value={draft[fieldKey]}
                              onChange={handleFieldChange(fieldKey)}
                              inputMode={meta.inputMode}
                              type={meta.type}
                              helperText={error ?? meta.helper}
                              error={Boolean(error)}
                              inputProps={{ 'data-testid': fieldTestId }}
                              slotProps={{
                                formHelperText: helperTextTestId
                                  ? ({
                                      'data-testid': helperTextTestId,
                                    } as unknown as HelperTextSlotProps)
                                  : undefined,
                              }}
                            />
                          </Grid>
                        )
                      })}
                    </Grid>

                    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                      <Button
                        variant="contained"
                        color="primary"
                        startIcon={<ContentCopyIcon />}
                        onClick={handleCopy}
                        data-testid="action-copy"
                        disabled={hasErrors}
                      >
                        Copy JSON
                      </Button>
                      <Button
                        variant="outlined"
                        color="primary"
                        startIcon={<DownloadIcon />}
                        onClick={handleDownload}
                        data-testid="action-download"
                        disabled={hasErrors}
                      >
                        Download JSON
                      </Button>
                      <Button
                        variant="text"
                        color="secondary"
                        startIcon={<RestartAltIcon />}
                        onClick={handleReset}
                      >
                        Reset
                      </Button>
                    </Stack>

                    {actionMessage ? (
                      <Alert
                        severity={actionMessage.kind}
                        onClose={() => setActionMessage(null)}
                        data-testid="action-feedback"
                      >
                        {actionMessage.text}
                      </Alert>
                    ) : null}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} lg={5}>
              <Stack spacing={3}>
                <Card
                  component="section"
                  variant="outlined"
                  data-testid="scenario-health-card"
                  sx={{
                    boxShadow: 1,
                    transition: 'box-shadow 0.3s ease',
                    '&:hover': { boxShadow: 3 },
                  }}
                >
                  <CardHeader
                    title="Health Snapshot"
                    titleTypographyProps={{ variant: 'h5', fontWeight: 600 }}
                    subheader="Real-time assessment of risk concentration, leverage, and operational hygiene."
                    subheaderTypographyProps={{ sx: { mt: 0.5 } }}
                  />
                  <CardContent>
                    <Stack spacing={3}>
                      <Box
                        sx={{
                          p: 3,
                          borderRadius: 2,
                          bgcolor:
                            scenarioHealth.status === 'Production-ready'
                              ? 'success.lighter'
                              : scenarioHealth.status === 'Needs review'
                                ? 'warning.lighter'
                                : 'error.lighter',
                          border: 1,
                          borderColor:
                            scenarioHealth.status === 'Production-ready'
                              ? 'success.main'
                              : scenarioHealth.status === 'Needs review'
                                ? 'warning.main'
                                : 'error.main',
                        }}
                      >
                        <Stack spacing={2}>
                          <Stack direction="row" alignItems="center" spacing={2}>
                            <Chip
                              icon={<StatusIcon />}
                              label={scenarioHealth.status}
                              color={statusChipColor}
                              size="medium"
                              data-testid="health-status"
                              sx={{ fontWeight: 600 }}
                            />
                          </Stack>
                          <Stack direction="row" alignItems="baseline" spacing={1}>
                            <Typography
                              variant="h4"
                              component="p"
                              data-testid="health-score"
                              sx={{
                                fontWeight: 700,
                                fontSize: { xs: '3rem', sm: '3.5rem' },
                              }}
                            >
                              {scenarioHealth.score}
                            </Typography>
                            <Typography
                              variant="h5"
                              color="text.secondary"
                              sx={{ fontSize: '1.5rem' }}
                            >
                              / 100
                            </Typography>
                          </Stack>
                          <LinearProgress
                            variant="determinate"
                            value={scenarioHealth.score}
                            aria-label="Scenario health score"
                            data-testid="health-meter"
                            sx={{
                              height: 8,
                              borderRadius: 4,
                            }}
                          />
                        </Stack>
                      </Box>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        data-testid="health-summary"
                      >
                        {scenarioHealth.summary}
                      </Typography>

                      {warnings.length > 0 ? (
                        <Alert severity="warning" data-testid="scenario-warnings">
                          <Stack spacing={1} data-testid="warning-list">
                            {warnings.map((warning) => (
                              <Typography key={warning} component="p" variant="body2">
                                {warning}
                              </Typography>
                            ))}
                          </Stack>
                        </Alert>
                      ) : (
                        <Alert severity="success" data-testid="scenario-no-warnings">
                          No risk warnings triggered. Document the assumptions before moving to
                          production.
                        </Alert>
                      )}

                      <List dense disablePadding sx={{ pl: 0 }} data-testid="scenario-checklist">
                        {scenarioHealth.checklist.map((item) => (
                          <ListItem key={item} sx={{ px: 0 }}>
                            <ListItemIcon sx={{ minWidth: 32 }}>
                              <CheckCircleIcon color="success" fontSize="small" />
                            </ListItemIcon>
                            <ListItemText
                              primaryTypographyProps={{ variant: 'body2' }}
                              primary={item}
                            />
                          </ListItem>
                        ))}
                      </List>
                    </Stack>
                  </CardContent>
                </Card>

                <Card
                  component="section"
                  variant="outlined"
                  data-testid="scenario-timeframe-card"
                  sx={{
                    boxShadow: 1,
                    transition: 'box-shadow 0.3s ease',
                    '&:hover': { boxShadow: 3 },
                  }}
                >
                  <CardHeader
                    title="Timeframe Insights"
                    titleTypographyProps={{ variant: 'h6', fontWeight: 600 }}
                    subheader="Operational considerations based on your execution interval."
                    subheaderTypographyProps={{ sx: { mt: 0.5 } }}
                  />
                  <CardContent>
                    {timeframeInsights.length === 0 ? (
                      <Alert severity="info">
                        Provide a valid timeframe to surface operational guidance.
                      </Alert>
                    ) : (
                      <List dense disablePadding sx={{ pl: 0 }}>
                        {timeframeInsights.map((insight) => (
                          <ListItem key={insight} sx={{ px: 0 }}>
                            <ListItemIcon sx={{ minWidth: 32 }}>
                              <WarningAmberIcon color="warning" fontSize="small" />
                            </ListItemIcon>
                            <ListItemText
                              primaryTypographyProps={{ variant: 'body2' }}
                              primary={insight}
                            />
                          </ListItem>
                        ))}
                      </List>
                    )}
                  </CardContent>
                </Card>

                <Paper
                  elevation={0}
                  variant="outlined"
                  component="section"
                  data-testid="scenario-preview"
                  sx={{
                    boxShadow: 1,
                    transition: 'box-shadow 0.3s ease',
                    '&:hover': { boxShadow: 3 },
                  }}
                >
                  <Box
                    sx={{
                      borderBottom: (theme) => `1px solid ${theme.palette.divider}`,
                      px: 3,
                      py: 2.5,
                      bgcolor: 'grey.50',
                    }}
                  >
                    <Typography variant="h6" component="h2" fontWeight={600}>
                      JSON Preview
                    </Typography>
                  </Box>
                  <Box sx={{ px: 3, py: 2.5 }}>
                    <Stack spacing={2}>
                      <Typography variant="body2" color="text.secondary">
                        This JSON payload matches the structure sent to the deployment pipeline.
                        Export when validation passes.
                      </Typography>
                      <Paper
                        variant="outlined"
                        sx={{
                          maxHeight: 320,
                          overflow: 'auto',
                          bgcolor: (theme) => theme.palette.grey[50],
                          borderColor: (theme) => theme.palette.grey[300],
                        }}
                      >
                        <Box
                          component="pre"
                          sx={{
                            m: 0,
                            p: 2,
                            fontSize: '0.875rem',
                            fontFamily: 'monospace',
                            lineHeight: 1.6,
                          }}
                        >
                          <code data-testid="scenario-json-preview">{preview}</code>
                        </Box>
                      </Paper>
                    </Stack>
                  </Box>
                </Paper>
              </Stack>
            </Grid>
          </Grid>
        </Stack>
      </Container>
    </Box>
  )
}

export function ScenarioStudioFallback() {
  return (
    <Box component="main" sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 4 }}>
      <Stack spacing={2} alignItems="center">
        <LinearProgress sx={{ width: 240, maxWidth: '60vw' }} />
        <Typography variant="body2" color="text.secondary">
          Preparing the Scenario Studio…
        </Typography>
      </Stack>
    </Box>
  )
}
