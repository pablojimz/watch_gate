import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { render } from '@/test/test-utils'
import { api, type UserSettings } from '@/api/client'
import { UserSettingsPage } from './UserSettingsPage'

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      getUserSettings: vi.fn(),
      changePassword: vi.fn(),
      putUserSettings: vi.fn(),
    },
  }
})

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)
const mockedToast = vi.mocked(toast)

const FIXTURE_SETTINGS: UserSettings = {
  login: 'jmartin',
  display_name: 'Javier Martín',
  role: 'mantenedor',
  repo_roles: [],
  github_api_url: 'https://api.github.com',
  github_token_set: false,
  ui_settings: null,
}

// Los campos de contraseña no usan <label for="..."> real -- solo un
// <span> hermano por encima del <Input> (ver UserSettingsPage.tsx) -- así
// que getByLabelText no los engancha. Se navega desde el texto visible
// hasta el <input> hermano en vez de depender del orden de los 4 inputs
// type="password" que hay en la página (el del token de GitHub incluido).
function getInputNextToText(text: string): HTMLInputElement {
  const label = screen.getByText(text)
  const input = label.parentElement?.querySelector('input')
  if (!input) throw new Error(`No se encontró el input junto a "${text}"`)
  return input as HTMLInputElement
}

async function fillPasswordForm(
  user: ReturnType<typeof userEvent.setup>,
  { current, next, confirm }: { current: string; next: string; confirm: string },
) {
  await user.type(getInputNextToText('Contraseña actual'), current)
  await user.type(getInputNextToText('Contraseña nueva'), next)
  await user.type(getInputNextToText('Confirmar contraseña nueva'), confirm)
}

describe('UserSettingsPage - cambio de contraseña', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.getUserSettings.mockResolvedValue(FIXTURE_SETTINGS)
  })

  it('rechaza una contraseña nueva demasiado corta sin llamar a la API', async () => {
    const user = userEvent.setup()
    render(<UserSettingsPage />)

    await screen.findByText('Cambiar contraseña', { selector: 'h2' })
    await fillPasswordForm(user, { current: 'oldpass1', next: 'short1', confirm: 'short1' })

    await user.click(screen.getByRole('button', { name: 'Cambiar contraseña' }))

    expect(mockedToast.error).toHaveBeenCalledWith(
      'La contraseña nueva debe tener al menos 8 caracteres',
    )
    expect(mockedApi.changePassword).not.toHaveBeenCalled()
  })

  it('rechaza confirmación que no coincide sin llamar a la API', async () => {
    const user = userEvent.setup()
    render(<UserSettingsPage />)

    await screen.findByText('Cambiar contraseña', { selector: 'h2' })
    await fillPasswordForm(user, {
      current: 'oldpass1',
      next: 'longenough1',
      confirm: 'doesNotMatch1',
    })

    await user.click(screen.getByRole('button', { name: 'Cambiar contraseña' }))

    expect(mockedToast.error).toHaveBeenCalledWith('Las contraseñas nuevas no coinciden')
    expect(mockedApi.changePassword).not.toHaveBeenCalled()
  })

  it('llama a la API con las contraseñas correctas y muestra un toast de éxito', async () => {
    const user = userEvent.setup()
    mockedApi.changePassword.mockResolvedValue(undefined)
    render(<UserSettingsPage />)

    await screen.findByText('Cambiar contraseña', { selector: 'h2' })
    await fillPasswordForm(user, {
      current: 'oldpass1',
      next: 'longenough1',
      confirm: 'longenough1',
    })

    await user.click(screen.getByRole('button', { name: 'Cambiar contraseña' }))

    await waitFor(() => {
      expect(mockedApi.changePassword).toHaveBeenCalledWith('oldpass1', 'longenough1')
    })
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('Contraseña actualizada')
    })

    // Los campos se limpian tras un cambio exitoso.
    await waitFor(() => {
      expect(getInputNextToText('Contraseña actual').value).toBe('')
      expect(getInputNextToText('Contraseña nueva').value).toBe('')
      expect(getInputNextToText('Confirmar contraseña nueva').value).toBe('')
    })
  })
})
