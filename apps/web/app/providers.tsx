'use client'

import type { ReactNode } from 'react'
import { ThemeProvider, createTheme, responsiveFontSizes } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'

const baseTheme = responsiveFontSizes(
  createTheme({
    palette: {
      mode: 'light',
      primary: {
        main: '#2563eb',
        contrastText: '#ffffff',
      },
      secondary: {
        main: '#0ea5e9',
        contrastText: '#ffffff',
      },
      background: {
        default: '#f5f7fb',
        paper: '#ffffff',
      },
      text: {
        primary: '#0f172a',
        secondary: '#475569',
      },
    },
    shape: {
      borderRadius: 14,
    },
    typography: {
      fontFamily: "'Inter', 'Roboto', 'Helvetica Neue', Helvetica, Arial, sans-serif",
      fontWeightRegular: 500,
      h3: {
        fontWeight: 700,
        letterSpacing: '-0.01em',
      },
      h4: {
        fontWeight: 700,
      },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: '#f5f7fb',
          },
          pre: {
            margin: 0,
            fontFamily:
              "'JetBrains Mono', 'Roboto Mono', 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
          },
          code: {
            fontFamily:
              "'JetBrains Mono', 'Roboto Mono', 'SFMono-Regular', Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 18,
            boxShadow:
              '0 24px 48px -24px rgba(15, 23, 42, 0.18), 0 12px 24px -18px rgba(15, 23, 42, 0.12)',
          },
        },
      },
      MuiButton: {
        defaultProps: {
          disableElevation: true,
        },
        styleOverrides: {
          root: {
            borderRadius: 999,
            fontWeight: 600,
            textTransform: 'none',
          },
        },
      },
      MuiAlert: {
        styleOverrides: {
          root: {
            borderRadius: 12,
          },
        },
      },
      MuiChip: {
        styleOverrides: {
          root: {
            fontWeight: 600,
            letterSpacing: 0.2,
          },
        },
      },
    },
  })
)

export function AppThemeProvider({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={baseTheme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  )
}
