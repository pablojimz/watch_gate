import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { render } from '@/test/test-utils'
import { api } from '@/api/client'
import AdminPage from './AdminPage'

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listRoles: vi.fn(),
      listUsers: vi.fn(),
      listRepos: vi.fn(),
      createUser: vi.fn(),
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

// La pestaña "access" (por defecto al montar) tiene DOS inputs con el
// mismo placeholder "Usuario": el de alta de usuario nuevo (primero en el
// DOM) y el del formulario de asignación de roles más abajo. Se toma el
// primero explícitamente en vez de asumir que getByPlaceholderText
// devuelve uno solo.
function getNewUserLoginInput(): HTMLInputElement {
  return screen.getAllByPlaceholderText('Usuario')[0] as HTMLInputElement
}

describe('AdminPage - alta de usuario (crear usuario)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.listRoles.mockResolvedValue([])
    mockedApi.listUsers.mockResolvedValue([])
    mockedApi.listRepos.mockResolvedValue([])
  })

  it('bloquea el alta si falta login/nombre o la contraseña es demasiado corta', async () => {
    const user = userEvent.setup()
    render(<AdminPage />)

    const createButton = await screen.findByRole('button', { name: 'Crear usuario' })

    // Ni login, ni nombre, ni contraseña rellenos -- debe fallar la
    // validación local sin llegar a tocar la API.
    await user.click(createButton)

    expect(mockedToast.error).toHaveBeenCalledWith(
      'Rellena usuario, nombre y una contraseña de al menos 8 caracteres',
    )
    expect(mockedApi.createUser).not.toHaveBeenCalled()

    // Con login y nombre pero contraseña corta (< 8), sigue bloqueado.
    mockedToast.error.mockClear()
    await user.type(getNewUserLoginInput(), 'nuevo.usuario')
    await user.type(screen.getByPlaceholderText('Nombre para mostrar'), 'Nuevo Usuario')
    await user.type(screen.getByPlaceholderText('Contraseña'), 'corta1')
    await user.click(createButton)

    expect(mockedToast.error).toHaveBeenCalledWith(
      'Rellena usuario, nombre y una contraseña de al menos 8 caracteres',
    )
    expect(mockedApi.createUser).not.toHaveBeenCalled()
  })

  it('crea el usuario cuando login, nombre y contraseña (>=8) son válidos', async () => {
    const user = userEvent.setup()
    mockedApi.createUser.mockResolvedValue({ login: 'nuevo.usuario', display_name: 'Nuevo Usuario' })
    render(<AdminPage />)

    const createButton = await screen.findByRole('button', { name: 'Crear usuario' })

    await user.type(getNewUserLoginInput(), 'Nuevo.Usuario')
    await user.type(screen.getByPlaceholderText('Nombre para mostrar'), 'Nuevo Usuario')
    await user.type(screen.getByPlaceholderText('Contraseña'), 'password123')
    await user.click(createButton)

    await waitFor(() => {
      // El login se normaliza a minúsculas antes de llamar a la API (ver
      // addUser en AdminPage.tsx); repo/rol iniciales quedan undefined
      // porque no se rellenaron.
      expect(mockedApi.createUser).toHaveBeenCalledWith(
        'nuevo.usuario',
        'Nuevo Usuario',
        'password123',
        undefined,
        undefined,
      )
    })
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith('Usuario creado')
    })
  })
})
