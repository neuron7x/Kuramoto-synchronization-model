import type { Metadata } from 'next'

import Link from 'next/link'
import dynamic from 'next/dynamic'

import Box from '@mui/material/Box'
import Container from '@mui/material/Container'
import Stack from '@mui/material/Stack'
import Typography from '@mui/material/Typography'

const SignInForm = dynamic(
  () =>
    import('./sign-in-form').then((mod) => ({
      default: mod.SignInForm,
    })),
  {
    loading: () => <SignInFormFallback />,
  }
)

function SignInFormFallback() {
  return (
    <Box
      component="section"
      role="status"
      aria-live="polite"
      sx={{
        borderRadius: 2,
        border: '1px solid',
        borderColor: 'divider',
        p: 4,
      }}
    >
      <Stack spacing={2} sx={{ textAlign: 'center' }}>
        <Typography component="p" variant="body1">
          Preparing sign-in form…
        </Typography>
        <Typography component="p" variant="body2" color="text.secondary">
          Secure authentication tools are being initialised.
        </Typography>
      </Stack>
    </Box>
  )
}

export const metadata: Metadata = {
  title: 'Sign in | TradePulse',
  description:
    'Access the TradePulse Scenario Studio with secure token handling and refresh support.',
}

export default function SignInPage() {
  return (
    <Box
      component="main"
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        py: { xs: 4, md: 8 },
        bgcolor: 'background.default',
      }}
    >
      <Container maxWidth="sm">
        <Stack spacing={{ xs: 3, md: 4 }}>
          <Stack spacing={2} textAlign="center">
            <Typography component="h1" variant="h3" fontWeight={700}>
              Welcome back
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Sign in to continue building resilient trading scenarios with guardrails and automatic
              health insights.
            </Typography>
          </Stack>
          <SignInForm />
          <Typography variant="body2" color="text.secondary" textAlign="center">
            Need access?{' '}
            <Link href="mailto:support@tradepulse.ai" style={{ fontWeight: 600 }}>
              Contact the TradePulse team
            </Link>
          </Typography>
        </Stack>
      </Container>
    </Box>
  )
}
