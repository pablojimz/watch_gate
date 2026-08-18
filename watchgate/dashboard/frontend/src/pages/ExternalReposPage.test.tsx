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
