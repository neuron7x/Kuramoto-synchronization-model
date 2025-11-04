import '@mui/material/styles'

declare module '@mui/material/styles' {
  interface PaletteColor {
    lighter?: string
  }

  interface SimplePaletteColorOptions {
    lighter?: string
  }
}
