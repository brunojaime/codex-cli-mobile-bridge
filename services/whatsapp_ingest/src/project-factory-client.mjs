export class ProjectFactoryClient {
  constructor({ baseUrl, timeoutMs = 5_000 }) {
    this.baseUrl = String(baseUrl).replace(/\/+$/, '')
    this.timeoutMs = timeoutMs
  }

  async ensureDraftForGroup({ groupId, subject }) {
    const marker = `[whatsapp-group:${groupId}]`
    const existing = await this.#listDrafts()
    const found = existing.find((draft) => String(draft.primary_goal || '').includes(marker))
    if (found) return { created: false, draftId: found.draft_id || found.id }

    const name = cleanSubject(subject).slice(0, 80) || 'Proyecto desde WhatsApp'
    const response = await this.#request('/project-factory/drafts', {
      method: 'POST',
      body: JSON.stringify({
        name,
        businessType: 'other',
        primaryGoal: `${marker} Proyecto provisional creado desde WhatsApp. Completar el relevamiento antes de inicializar el workspace.`,
        slug: slugify(name),
        guidedIntakeEnabled: true,
        creationMode: 'product',
      }),
    })
    const draftId = response.draft_id || response.id
    if (!draftId) throw new Error('Project Factory returned a draft without an id')
    return { created: true, draftId }
  }

  async #listDrafts() {
    const response = await this.#request('/project-factory/drafts?limit=100')
    return Array.isArray(response.drafts) ? response.drafts : []
  }

  async #request(pathname, options = {}) {
    const response = await fetch(`${this.baseUrl}${pathname}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
      signal: AbortSignal.timeout(this.timeoutMs),
    })
    if (!response.ok) {
      const detail = (await response.text()).slice(0, 500)
      throw new Error(`Project Factory ${response.status}: ${detail}`)
    }
    return response.json()
  }
}

function cleanSubject(value) {
  return String(value || '').trim().replace(/^nienfos\s*[·:|/-]\s*/i, '').trim()
}

function slugify(value) {
  const slug = String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
    .replace(/-+$/g, '')
  return slug || 'proyecto-whatsapp'
}
