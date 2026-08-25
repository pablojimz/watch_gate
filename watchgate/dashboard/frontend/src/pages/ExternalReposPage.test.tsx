import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { render } from '@/test/test-utils'
import { api, type MonitoredRepoResponse } from '@/api/client'
import ExternalReposPage from './ExternalReposPage'

// Se mockean tanto `api` como `sonner` para poder aislar exclusivamente el
// flujo handleDeleteRepo: sin esto el test dependería de un backend real
// (api.listExternalRepos en el mount) y no podríamos aserar qué toast se
// disparó sin renderizar el <Toaster/> real de sonner.
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listExternalRepos: vi.fn(),
      deleteExternalRepo: vi.fn(),
      getGithubAppInfo: vi.fn(),
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

const FIXTURE_REPO: MonitoredRepoResponse = {
  id: 'repo-123',
  vcs_connection_id: null,
  repo_path: 'acme/payments-api',
  monitor_type: 'audited',
  status: 'ok',
  last_scanned_at: null,
  last_polled_at: null,
  consecutive_errors: 0,
  created_at: '2026-01-01T00:00:00Z',
}

describe('ExternalReposPage - handleDeleteRepo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.listExternalRepos.mockResolvedValue([FIXTURE_REPO])
    mockedApi.getGithubAppInfo.mockResolvedValue({ configured: false, install_url: null })
  })

  it('pide confirmación, borra el repo y muestra un toast de éxito si el usuario confirma', async () => {
    const user = userEvent.setup()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    mockedApi.deleteExternalRepo.mockResolvedValue(undefined)

    render(<ExternalReposPage />)

    const deleteButton = await screen.findByRole('button', { name: 'Eliminar' })
    await user.click(deleteButton)

    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(confirmSpy.mock.calls[0][0]).toContain('acme/payments-api')

    await waitFor(() => {
      expect(mockedApi.deleteExternalRepo).toHaveBeenCalledWith('repo-123')
    })
    await waitFor(() => {
      expect(mockedToast.success).toHaveBeenCalledWith(
        'Repositorio eliminado de la monitorización.',
      )
    })
  })

  it('no llama a la API si el usuario cancela la confirmación', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(false)

    render(<ExternalReposPage />)

    const deleteButton = await screen.findByRole('button', { name: 'Eliminar' })
    await user.click(deleteButton)

    expect(window.confirm).toHaveBeenCalledTimes(1)
    expect(mockedApi.deleteExternalRepo).not.toHaveBeenCalled()
    expect(mockedToast.success).not.toHaveBeenCalled()
  })
})

describe('ExternalReposPage - botón de instalar la GitHub App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedApi.listExternalRepos.mockResolvedValue([FIXTURE_REPO])
  })

  it('muestra el botón de instalación cuando el backend anuncia la App', async () => {
    mockedApi.getGithubAppInfo.mockResolvedValue({
      configured: true,
      install_url: 'https://github.com/apps/watchgate/installations/new',
    })

    render(<ExternalReposPage />)

    const installLink = await screen.findByRole('link', { name: /Instalar GitHub App/ })
    expect(installLink).toHaveAttribute(
      'href',
      'https://github.com/apps/watchgate/installations/new',
    )
  })

  it('no muestra el botón cuando la App no está anunciada (install_url null)', async () => {
    mockedApi.getGithubAppInfo.mockResolvedValue({ configured: false, install_url: null })

    render(<ExternalReposPage />)

    await screen.findByText('acme/payments-api')
    expect(screen.queryByRole('link', { name: /Instalar GitHub App/ })).toBeNull()
  })
})
