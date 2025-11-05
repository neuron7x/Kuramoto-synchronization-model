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
      success: {
        main: '#10b981',
        light: '#34d399',
        lighter: '#d1fae5',
      },
      warning: {
        main: '#f59e0b',
        light: '#fbbf24',
        lighter: '#fef3c7',
      },
      error: {
        main: '#ef4444',
        light: '#f87171',
        lighter: '#fee2e2',
      },
      background: {
        default: '#f8fafc',
        paper: '#ffffff',
      },
      text: {
        primary: '#0f172a',
        secondary: '#475569',
      },
    },
    shape: {
      borderRadius: 12,
    },
    typography: {
      fontFamily: "'Inter', 'Roboto', 'Helvetica Neue', Helvetica, Arial, sans-serif",
      fontWeightRegular: 500,
      h3: {
        fontWeight: 700,
        letterSpacing: '-0.02em',
      },
      h4: {
        fontWeight: 700,
      },
      h5: {
        fontWeight: 600,
      },
      h6: {
        fontWeight: 600,
      },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: {
            backgroundColor: '#f8fafc',
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
            borderRadius: 16,
            border: '1px solid',
            borderColor: '#e2e8f0',
          },
        },
      },
      MuiButton: {
        defaultProps: {
          disableElevation: true,
        },
        styleOverrides: {
          root: {
            borderRadius: 8,
            fontWeight: 600,
            textTransform: 'none',
            paddingTop: 10,
            paddingBottom: 10,
          },
          contained: {
            boxShadow: 'none',
            '&:hover': {
              boxShadow: '0 4px 12px rgba(37, 99, 235, 0.2)',
            },
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
            letterSpacing: 0.3,
          },
        },
      },
      MuiLinearProgress: {
        styleOverrides: {
          root: {
            borderRadius: 4,
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
