'use client'

import { useCallback } from 'react'

import AppBar from '@mui/material/AppBar'
import Button from '@mui/material/Button'
import Container from '@mui/material/Container'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'

import LogoutIcon from '@mui/icons-material/Logout'
import ShowChartIcon from '@mui/icons-material/ShowChart'

import { useAuth } from '../../auth/auth-provider'

export function AppHeader() {
  const { signOut } = useAuth()

  const handleSignOut = useCallback(async () => {
    try {
      await signOut()
    } catch (error) {
      console.error('Sign-out failed', error)
    }
  }, [signOut])

  return (
    <AppBar position="sticky" color="default" elevation={0}>
      <Container maxWidth="xl">
        <Toolbar disableGutters sx={{ minHeight: { xs: 56, sm: 64 } }}>
          <ShowChartIcon sx={{ mr: 1.5, color: 'primary.main' }} />
          <Typography
            variant="h6"
            component="div"
            sx={{
              flexGrow: 1,
              fontWeight: 600,
              color: 'text.primary',
            }}
          >
            TradePulse
          </Typography>
          <Button
            color="inherit"
            startIcon={<LogoutIcon />}
            onClick={handleSignOut}
            size="small"
            sx={{ textTransform: 'none' }}
          >
            Sign out
          </Button>
        </Toolbar>
      </Container>
    </AppBar>
  )
}
