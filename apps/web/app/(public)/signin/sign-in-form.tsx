'use client'

import { useCallback, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'

import LoadingButton from '@mui/lab/LoadingButton'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'

import { useAuth } from '../../auth/auth-provider'

type FormState = {
  email: string
  password: string
}

const INITIAL_FORM_STATE: FormState = {
  email: '',
  password: '',
}

export function SignInForm() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM_STATE)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const { signIn, status } = useAuth()

  const isDisabled = useMemo(() => submitting || status === 'loading', [status, submitting])

  const handleChange = (field: keyof FormState) => (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value
    setForm((previous) => ({ ...previous, [field]: value }))
  }

  const handleSubmit = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      setSubmitting(true)
      setError(null)

      try {
        if (!form.email || !form.password) {
          throw new Error('Enter both email and password to continue.')
        }

        const now = Date.now()
        const accessToken = crypto.randomUUID()
        const refreshToken = crypto.randomUUID()

        await signIn({
          accessToken,
          accessTokenExpiresAt: now + 15 * 60 * 1000,
          refreshToken,
          refreshTokenExpiresAt: now + 7 * 24 * 60 * 60 * 1000,
        })

        setForm(INITIAL_FORM_STATE)
      } catch (cause) {
        console.error('Sign-in failed', cause)
        setError(cause instanceof Error ? cause.message : 'Unable to sign in. Please try again.')
      } finally {
        setSubmitting(false)
      }
    },
    [form.email, form.password, signIn]
  )

  return (
    <Card component="section" variant="outlined" sx={{ boxShadow: 1 }}>
      <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
        <Stack component="form" spacing={3} onSubmit={handleSubmit} noValidate>
          <TextField
            label="Work email"
            type="email"
            name="email"
            autoComplete="email"
            value={form.email}
            onChange={handleChange('email')}
            disabled={isDisabled}
            required
            fullWidth
            helperText="Enter your GeoSync work email address"
            slotProps={{
              htmlInput: {
                'aria-label': 'Work email',
              },
            }}
          />
          <TextField
            label="Password"
            type="password"
            name="password"
            autoComplete="current-password"
            value={form.password}
            onChange={handleChange('password')}
            disabled={isDisabled}
            required
            fullWidth
            helperText="Enter your account password"
            slotProps={{
              htmlInput: {
                'aria-label': 'Password',
              },
            }}
          />
          {error ? (
            <Alert severity="error" role="alert" aria-live="polite">
              {error}
            </Alert>
          ) : null}
          <Box>
            <LoadingButton
              type="submit"
              variant="contained"
              fullWidth
              loading={submitting}
              disabled={isDisabled}
              size="large"
              aria-label={submitting ? 'Signing in...' : 'Sign in to GeoSync'}
            >
              Continue
            </LoadingButton>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}
