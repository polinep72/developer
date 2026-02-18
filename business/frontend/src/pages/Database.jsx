import { useState, useEffect } from 'react'
import { getChips, createChip, updateChip, getBodies, createBody, updateBody, getCovers, createCover, updateCover } from '../api/db'
import { getWorks, createWork, updateWork, deleteWork } from '../api/works'
import './Database.css'

const CAN_EDIT_DB = ['admin', 'accountant']
const CAN_EDIT_WORKS = ['admin', 'developer']

function filterBySearch(list, search, getFields) {
  if (!search || !search.trim()) return list
  const q = search.trim().toLowerCase()
  return list.filter((item) =>
    getFields(item).some((v) => v != null && String(v).toLowerCase().includes(q))
  )
}

function Database() {
  const [activeTab, setActiveTab] = useState('chips')
  const [searchQuery, setSearchQuery] = useState('')
  const [chips, setChips] = useState([])
  const [bodies, setBodies] = useState([])
  const [covers, setCovers] = useState([])
  const [works, setWorks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savingId, setSavingId] = useState(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newItem, setNewItem] = useState({})
  const [showCreateWorkForm, setShowCreateWorkForm] = useState(false)
  const [newWork, setNewWork] = useState({})
  const [editingWork, setEditingWork] = useState(null)
  const [deletingWorkId, setDeletingWorkId] = useState(null)

  const currentUser = (() => {
    try {
      const s = window.localStorage.getItem('ccs_user')
      return s ? JSON.parse(s) : null
    } catch {
      return null
    }
  })()
  const canEdit = currentUser && CAN_EDIT_DB.includes(currentUser.role)
  const canEditWorks = currentUser && CAN_EDIT_WORKS.includes(currentUser.role)

  const filteredChips = filterBySearch(chips, searchQuery, (r) => [r.chip_code, r.decimal_code, r.chip_name, r.description])
  const filteredBodies = filterBySearch(bodies, searchQuery, (r) => [r.body_type, r.decimal_code, r.body_name, r.description, r.material])
  const filteredCovers = filterBySearch(covers, searchQuery, (r) => [r.decimal_code, r.classifier_description, r.for_body, r.cover_cost, r.run_norm])
  const filteredWorks = filterBySearch(works, searchQuery, (r) => [r.наименование, r.тип_работы, r.категория, r.описание])

  useEffect(() => {
    if (activeTab === 'chips') loadChips()
    else if (activeTab === 'bodies') loadBodies()
    else if (activeTab === 'covers') loadCovers()
    else if (activeTab === 'works') loadWorks()
    setShowCreateForm(false)
    setNewItem({})
    setShowCreateWorkForm(false)
    setNewWork({})
    setEditingWork(null)
    setError('')
  }, [activeTab])

  const loadChips = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getChips()
      setChips(data)
    } catch (e) {
      setError(e.userMessage || e.response?.data?.detail || e.message || 'Ошибка загрузки кристаллов')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const loadBodies = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getBodies()
      setBodies(data)
    } catch (e) {
      const msg = e.userMessage || e.response?.data?.detail || e.message
      setError(typeof msg === 'string' ? msg : 'Ошибка загрузки корпусов')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const loadCovers = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getCovers()
      setCovers(data)
    } catch (e) {
      const msg = e.userMessage || e.response?.data?.detail || e.message
      setError(typeof msg === 'string' ? msg : 'Ошибка загрузки крышек')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const loadWorks = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await getWorks()
      setWorks(Array.isArray(data) ? data : [])
    } catch (e) {
      const msg = e.userMessage || e.response?.data?.detail || e.message
      setError(typeof msg === 'string' ? msg : 'Ошибка загрузки видов работ')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateWork = async () => {
    if (!newWork.наименование || !String(newWork.наименование).trim()) {
      setError('Наименование обязательно')
      return
    }
    setError('')
    try {
      const payload = {
        наименование: String(newWork.наименование).trim(),
        тип_работы: newWork.тип_работы ? String(newWork.тип_работы).trim() : null,
        категория: newWork.категория ? String(newWork.категория).trim() : null,
        описание: newWork.описание ? String(newWork.описание).trim() : null,
        активна: newWork.активна !== false,
      }
      if (newWork.labor_hours !== '' && newWork.labor_hours != null) payload.labor_hours = parseFloat(newWork.labor_hours)
      if (newWork.hour_rate !== '' && newWork.hour_rate != null) payload.hour_rate = parseFloat(newWork.hour_rate)
      if (newWork.base_wage !== '' && newWork.base_wage != null) payload.base_wage = parseFloat(newWork.base_wage)
      const created = await createWork(payload)
      setWorks((prev) => [...prev, created].sort((a, b) => (a.наименование || '').localeCompare(b.наименование || '')))
      setShowCreateWorkForm(false)
      setNewWork({})
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка создания вида работ')
    }
  }

  const handleUpdateWork = async () => {
    if (!editingWork || !editingWork.id) return
    if (!editingWork.наименование || !String(editingWork.наименование).trim()) {
      setError('Наименование обязательно')
      return
    }
    setError('')
    try {
      const payload = {
        наименование: String(editingWork.наименование).trim(),
        тип_работы: editingWork.тип_работы != null ? String(editingWork.тип_работы).trim() : null,
        категория: editingWork.категория != null ? String(editingWork.категория).trim() : null,
        описание: editingWork.описание != null ? String(editingWork.описание).trim() : null,
        активна: editingWork.активна,
      }
      if (editingWork.labor_hours !== '' && editingWork.labor_hours != null) payload.labor_hours = parseFloat(editingWork.labor_hours)
      else if (editingWork.labor_hours === '') payload.labor_hours = null
      if (editingWork.hour_rate !== '' && editingWork.hour_rate != null) payload.hour_rate = parseFloat(editingWork.hour_rate)
      else if (editingWork.hour_rate === '') payload.hour_rate = null
      if (editingWork.base_wage !== '' && editingWork.base_wage != null) payload.base_wage = parseFloat(editingWork.base_wage)
      else if (editingWork.base_wage === '') payload.base_wage = null
      const updated = await updateWork(editingWork.id, payload)
      setWorks((prev) => prev.map((w) => (w.id === updated.id ? updated : w)))
      setEditingWork(null)
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка сохранения')
    }
  }

  const handleDeleteWork = async (workId) => {
    if (!window.confirm('Удалить этот вид работ?')) return
    setDeletingWorkId(workId)
    try {
      await deleteWork(workId)
      setWorks((prev) => prev.filter((w) => w.id !== workId))
      if (editingWork && editingWork.id === workId) setEditingWork(null)
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка удаления')
    } finally {
      setDeletingWorkId(null)
    }
  }

  const openWorkCard = (work) => {
    setEditingWork({
      id: work.id,
      наименование: work.наименование ?? '',
      тип_работы: work.тип_работы ?? '',
      категория: work.категория ?? '',
      описание: work.описание ?? '',
      активна: work.активна !== false,
      labor_hours: work.labor_hours != null ? String(work.labor_hours) : '',
      hour_rate: work.hour_rate != null ? String(work.hour_rate) : '',
      base_wage: work.base_wage != null ? String(work.base_wage) : '',
    })
    setError('')
  }

  const handleSaveChip = async (item) => {
    setSavingId(item.id)
    try {
      await updateChip(item.id, { chip_name: item.chip_name, description: item.description, chip_cost: item.chip_cost != null && item.chip_cost !== '' ? Number(item.chip_cost) : null })
      setChips((prev) => prev.map((r) => (r.id === item.id ? { ...r, ...item } : r)))
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSavingId(null)
    }
  }

  const handleSaveBody = async (item) => {
    setSavingId(item.id)
    try {
      await updateBody(item.id, {
        body_type: item.body_type,
        body_name: item.body_name,
        description: item.description,
        material: item.material,
        body_cost: item.body_cost != null && item.body_cost !== '' ? Number(item.body_cost) : null,
        run_norm: item.run_norm != null && item.run_norm !== '' ? Number(item.run_norm) : null,
      })
      setBodies((prev) => prev.map((r) => (r.id === item.id ? { ...r, ...item } : r)))
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSavingId(null)
    }
  }

  const handleSaveCover = async (item) => {
    setSavingId(item.id)
    try {
      await updateCover(item.id, {
        cover_cost: item.cover_cost != null && item.cover_cost !== '' ? Number(item.cover_cost) : null,
        run_norm: item.run_norm != null && item.run_norm !== '' ? Number(item.run_norm) : null,
      })
      setCovers((prev) => prev.map((r) => (r.id === item.id ? { ...r, ...item } : r)))
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка сохранения')
    } finally {
      setSavingId(null)
    }
  }

  const updateChipField = (id, field, value) => {
    setChips((prev) => prev.map((r) => (r.id === id ? { ...r, [field]: value } : r)))
  }
  const updateBodyField = (id, field, value) => {
    setBodies((prev) => prev.map((r) => (r.id === id ? { ...r, [field]: value } : r)))
  }
  const updateCoverField = (id, field, value) => {
    setCovers((prev) => prev.map((r) => (r.id === id ? { ...r, [field]: value } : r)))
  }

  const handleCreateChip = async () => {
    if (!newItem.chip_code || !newItem.chip_code.trim()) {
      setError('Код кристалла обязателен')
      return
    }
    setError('')
    try {
      const created = await createChip({
        chip_code: newItem.chip_code.trim(),
        chip_name: newItem.chip_name?.trim() || null,
        description: newItem.description?.trim() || null,
        chip_cost: newItem.chip_cost ? Number(newItem.chip_cost) : null,
      })
      setChips((prev) => [...prev, created].sort((a, b) => a.chip_code.localeCompare(b.chip_code)))
      setShowCreateForm(false)
      setNewItem({})
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка создания кристалла')
    }
  }

  const handleCreateBody = async () => {
    setError('')
    try {
      const created = await createBody({
        body_type: newItem.body_type?.trim() || null,
        body_name: newItem.body_name?.trim() || null,
        description: newItem.description?.trim() || null,
        material: newItem.material?.trim() || null,
        body_cost: newItem.body_cost ? Number(newItem.body_cost) : null,
        run_norm: newItem.run_norm ? Number(newItem.run_norm) : null,
      })
      setBodies((prev) => [...prev, created].sort((a, b) => (a.body_type || '').localeCompare(b.body_type || '')))
      setShowCreateForm(false)
      setNewItem({})
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка создания корпуса')
    }
  }

  const handleCreateCover = async () => {
    const dcdId = String(newItem.dcd_id || '').trim()
    if (!dcdId) {
      setError('dcd_id обязателен')
      return
    }
    setError('')
    try {
      const created = await createCover({
        dcd_id: Number(dcdId),
        cover_cost: newItem.cover_cost ? Number(newItem.cover_cost) : null,
        run_norm: newItem.run_norm ? Number(newItem.run_norm) : null,
      })
      setCovers((prev) =>
        [...prev, created].sort((a, b) =>
          String(a.decimal_code || '').localeCompare(String(b.decimal_code || ''))
        )
      )
      setShowCreateForm(false)
      setNewItem({})
    } catch (e) {
      setError(e.response?.data?.detail || 'Ошибка создания крышки')
    }
  }

  const handleCancelCreate = () => {
    setShowCreateForm(false)
    setNewItem({})
    setError('')
  }

  const sectionTitle =
    activeTab === 'chips'
      ? 'Кристаллы (таблица chips)'
      : activeTab === 'bodies'
        ? 'Корпуса (таблица bodies)'
        : activeTab === 'covers'
          ? 'Крышки (таблица covers)'
          : 'Вид работ (таблица works)'

  return (
    <div className="database-page">
      <div className="db-sticky-header">
        <h1 className="page-title">База данных</h1>

        <div className="db-tabs-and-search">
          <div className="db-tabs">
            <button
              type="button"
              className={`db-tab ${activeTab === 'chips' ? 'active' : ''}`}
              onClick={() => setActiveTab('chips')}
            >
              Кристаллы
            </button>
            <button
              type="button"
              className={`db-tab ${activeTab === 'bodies' ? 'active' : ''}`}
              onClick={() => setActiveTab('bodies')}
            >
              Корпуса
            </button>
            <button
              type="button"
              className={`db-tab ${activeTab === 'covers' ? 'active' : ''}`}
              onClick={() => setActiveTab('covers')}
            >
              Крышки
            </button>
            <button
              type="button"
              className={`db-tab ${activeTab === 'works' ? 'active' : ''}`}
              onClick={() => setActiveTab('works')}
            >
              Вид работ
            </button>
          </div>
          <div className="db-search-row">
            <label htmlFor="db-search" className="db-search-label">Поиск:</label>
            <input
              id="db-search"
              type="text"
              className="db-search-input"
              placeholder={
                activeTab === 'chips'
                  ? 'По коду, децимальному коду или описанию кристалла...'
                  : activeTab === 'bodies'
                    ? 'По типу, децимальному коду, описанию или материалу корпуса...'
                    : activeTab === 'covers'
                      ? 'По децимальному коду или описанию крышки...'
                      : 'По наименованию, типу работы или категории...'
              }
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>

        <h2 className="db-section-title">{sectionTitle}</h2>
        {canEdit && activeTab !== 'works' && (
          <div style={{ marginTop: '12px' }}>
            {!showCreateForm ? (
              <button
                type="button"
                className="db-add-btn"
                onClick={() => setShowCreateForm(true)}
              >
                + Добавить новый материал
              </button>
            ) : (
              <button
                type="button"
                className="db-cancel-btn"
                onClick={handleCancelCreate}
              >
                Отмена
              </button>
            )}
          </div>
        )}
        {canEditWorks && activeTab === 'works' && (
          <div style={{ marginTop: '12px' }}>
            {!showCreateWorkForm ? (
              <button
                type="button"
                className="db-add-btn"
                onClick={() => setShowCreateWorkForm(true)}
              >
                + Добавить новый вид работ
              </button>
            ) : (
              <button
                type="button"
                className="db-cancel-btn"
                onClick={() => { setShowCreateWorkForm(false); setNewWork({}); setError('') }}
              >
                Отмена
              </button>
            )}
          </div>
        )}
      </div>

      <div className="db-tab-content">
        {error && <div className="db-error">{error}</div>}

        {showCreateForm && canEdit && (
          <div className="db-create-form">
            {activeTab === 'chips' && (
              <div className="db-form-row">
                <label>Код*:</label>
                <input
                  type="text"
                  value={newItem.chip_code || ''}
                  onChange={(e) => setNewItem({ ...newItem, chip_code: e.target.value })}
                  className="db-input"
                  placeholder="Введите код кристалла"
                />
                <label>Наименование:</label>
                <input
                  type="text"
                  value={newItem.chip_name || ''}
                  onChange={(e) => setNewItem({ ...newItem, chip_name: e.target.value })}
                  className="db-input"
                  placeholder="Введите наименование"
                />
                <label>Описание:</label>
                <input
                  type="text"
                  value={newItem.description || ''}
                  onChange={(e) => setNewItem({ ...newItem, description: e.target.value })}
                  className="db-input"
                  placeholder="Введите описание"
                />
                <label>Закуп. стоимость:</label>
                <input
                  type="number"
                  step="any"
                  value={newItem.chip_cost || ''}
                  onChange={(e) => setNewItem({ ...newItem, chip_cost: e.target.value })}
                  className="db-input db-input-num"
                  placeholder="0.00"
                />
                <button type="button" className="db-save-btn" onClick={handleCreateChip}>
                  Создать
                </button>
              </div>
            )}
            {activeTab === 'bodies' && (
              <div className="db-form-row">
                <label>Тип корпуса:</label>
                <input
                  type="text"
                  value={newItem.body_type || ''}
                  onChange={(e) => setNewItem({ ...newItem, body_type: e.target.value })}
                  className="db-input"
                  placeholder="Введите тип корпуса"
                />
                <label>Наименование:</label>
                <input
                  type="text"
                  value={newItem.body_name || ''}
                  onChange={(e) => setNewItem({ ...newItem, body_name: e.target.value })}
                  className="db-input db-input-name"
                  placeholder="Введите наименование"
                />
                <label>Описание:</label>
                <input
                  type="text"
                  value={newItem.description || ''}
                  onChange={(e) => setNewItem({ ...newItem, description: e.target.value })}
                  className="db-input"
                  placeholder="Введите описание"
                />
                <label>Материал:</label>
                <input
                  type="text"
                  value={newItem.material || ''}
                  onChange={(e) => setNewItem({ ...newItem, material: e.target.value })}
                  className="db-input"
                  placeholder="ID материала"
                />
                <label>Закуп. стоимость:</label>
                <input
                  type="number"
                  step="any"
                  value={newItem.body_cost || ''}
                  onChange={(e) => setNewItem({ ...newItem, body_cost: e.target.value })}
                  className="db-input db-input-num"
                  placeholder="0.00"
                />
                <label>Норма расхода:</label>
                <input
                  type="number"
                  step="any"
                  value={newItem.run_norm || ''}
                  onChange={(e) => setNewItem({ ...newItem, run_norm: e.target.value })}
                  className="db-input db-input-num"
                  placeholder="0.00"
                />
                <button type="button" className="db-save-btn" onClick={handleCreateBody}>
                  Создать
                </button>
              </div>
            )}
            {activeTab === 'covers' && (
              <div className="db-form-row">
                <label>dcd_id*:</label>
                <input
                  type="number"
                  value={newItem.dcd_id || ''}
                  onChange={(e) => setNewItem({ ...newItem, dcd_id: e.target.value })}
                  className="db-input"
                  placeholder="ID из tlvsh_serial_numbers"
                />
                <label>Закуп. стоимость:</label>
                <input
                  type="number"
                  step="any"
                  value={newItem.cover_cost || ''}
                  onChange={(e) => setNewItem({ ...newItem, cover_cost: e.target.value })}
                  className="db-input db-input-num"
                  placeholder="0.00"
                />
                <label>Норма расхода:</label>
                <input
                  type="number"
                  step="any"
                  value={newItem.run_norm || ''}
                  onChange={(e) => setNewItem({ ...newItem, run_norm: e.target.value })}
                  className="db-input db-input-num"
                  placeholder="0.00"
                />
                <button type="button" className="db-save-btn" onClick={handleCreateCover}>
                  Создать
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'works' && showCreateWorkForm && canEditWorks && (
          <div className="db-create-form db-work-form">
            <div className="db-form-row">
              <label>Наименование *:</label>
              <input
                type="text"
                value={newWork.наименование ?? ''}
                onChange={(e) => setNewWork({ ...newWork, наименование: e.target.value })}
                className="db-input"
                placeholder="Введите наименование работы"
              />
              <label>Тип работ:</label>
              <input
                type="text"
                value={newWork.тип_работы ?? ''}
                onChange={(e) => setNewWork({ ...newWork, тип_работы: e.target.value })}
                className="db-input"
                placeholder="Тип работы"
              />
              <label>Категория:</label>
              <input
                type="text"
                value={newWork.категория ?? ''}
                onChange={(e) => setNewWork({ ...newWork, категория: e.target.value })}
                className="db-input"
                placeholder="Категория"
              />
              <label>Трудоёмкость, н/час:</label>
              <input
                type="number"
                step="0.0001"
                value={newWork.labor_hours ?? ''}
                onChange={(e) => setNewWork({ ...newWork, labor_hours: e.target.value })}
                className="db-input db-input-num"
                placeholder="0"
              />
              <label>Стоимость н/час (руб.):</label>
              <input
                type="number"
                step="0.01"
                value={newWork.hour_rate ?? ''}
                onChange={(e) => setNewWork({ ...newWork, hour_rate: e.target.value })}
                className="db-input db-input-num"
                placeholder="0"
              />
              <button type="button" className="db-save-btn" onClick={handleCreateWork}>
                Создать
              </button>
            </div>
          </div>
        )}

        {activeTab === 'chips' && (
          <div className="db-section">
            {loading ? (
              <p className="db-loading">Загрузка...</p>
            ) : (
              <div className="db-table-wrapper">
                <table className="db-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Код</th>
                      <th>Децимальный код</th>
                      <th>Описание</th>
                      <th>Закуп. стоимость</th>
                      {canEdit && <th>Действия</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredChips.length === 0 ? (
                      <tr>
                        <td colSpan={canEdit ? 6 : 5} className="db-empty">
                          {chips.length === 0 ? 'Нет данных' : 'Ничего не найдено по запросу'}
                        </td>
                      </tr>
                    ) : (
                      filteredChips.map((row) => (
                        <tr key={row.id}>
                          <td>{row.id}</td>
                          <td>{row.chip_code}</td>
                          <td>
                            {row.decimal_code ?? '—'}
                          </td>
                          <td>
                            {canEdit ? (
                              <input
                                type="text"
                                value={row.description ?? ''}
                                onChange={(e) => updateChipField(row.id, 'description', e.target.value)}
                                className="db-input"
                              />
                            ) : (
                              row.description ?? '—'
                            )}
                          </td>
                          <td>
                            {canEdit ? (
                              <input
                                type="number"
                                step="any"
                                value={row.chip_cost ?? ''}
                                onChange={(e) => updateChipField(row.id, 'chip_cost', e.target.value)}
                                className="db-input db-input-num"
                              />
                            ) : (
                              row.chip_cost != null ? row.chip_cost : '—'
                            )}
                          </td>
                          {canEdit && (
                            <td>
                              <button
                                type="button"
                                className="db-save-btn"
                                onClick={() => handleSaveChip(row)}
                                disabled={savingId === row.id}
                              >
                                {savingId === row.id ? 'Сохранение...' : 'Сохранить'}
                              </button>
                            </td>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'bodies' && (
          <div className="db-section">
            {loading ? (
              <p className="db-loading">Загрузка...</p>
            ) : (
              <div className="db-table-wrapper">
                <table className="db-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Тип корпуса</th>
                      <th>Децимальный код</th>
                      <th>Описание</th>
                      <th>Закуп. стоимость</th>
                      <th>Норма расхода</th>
                      {canEdit && <th>Действия</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredBodies.length === 0 ? (
                      <tr>
                        <td colSpan={canEdit ? 7 : 6} className="db-empty">
                          {bodies.length === 0 ? 'Нет данных' : 'Ничего не найдено по запросу'}
                        </td>
                      </tr>
                    ) : (
                      filteredBodies.map((row) => (
                        <tr key={row.id}>
                          <td>{row.id}</td>
                          <td>
                            {canEdit ? (
                              <input
                                type="text"
                                value={row.body_type ?? ''}
                                onChange={(e) => updateBodyField(row.id, 'body_type', e.target.value)}
                                className="db-input db-input-sm"
                              />
                            ) : (
                              row.body_type ?? '—'
                            )}
                          </td>
                          <td>
                            {row.decimal_code ?? '—'}
                          </td>
                          <td>
                            {canEdit ? (
                              <input
                                type="text"
                                value={row.description ?? ''}
                                onChange={(e) => updateBodyField(row.id, 'description', e.target.value)}
                                className="db-input"
                              />
                            ) : (
                              (row.description && row.description.slice(0, 40)) || '—'
                            )}
                          </td>
                          <td>
                            {canEdit ? (
                              <input
                                type="number"
                                step="any"
                                value={row.body_cost ?? ''}
                                onChange={(e) => updateBodyField(row.id, 'body_cost', e.target.value)}
                                className="db-input db-input-num"
                              />
                            ) : (
                              row.body_cost != null ? row.body_cost : '—'
                            )}
                          </td>
                          <td>
                            {canEdit ? (
                              <input
                                type="number"
                                step="any"
                                value={row.run_norm ?? ''}
                                onChange={(e) => updateBodyField(row.id, 'run_norm', e.target.value)}
                                className="db-input db-input-num"
                              />
                            ) : (
                              row.run_norm != null ? row.run_norm : '—'
                            )}
                          </td>
                          {canEdit && (
                            <td>
                              <button
                                type="button"
                                className="db-save-btn"
                                onClick={() => handleSaveBody(row)}
                                disabled={savingId === row.id}
                              >
                                {savingId === row.id ? '...' : 'Сохранить'}
                              </button>
                            </td>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'covers' && (
          <div className="db-section">
            {loading ? (
              <p className="db-loading">Загрузка...</p>
            ) : (
              <div className="db-table-wrapper">
                <table className="db-table">
                  <thead>
                    <tr>
                      <th>№</th>
                      <th>Децимальный код</th>
                      <th>Описание</th>
                      <th>Для корпуса</th>
                      <th>Закуп. стоимость</th>
                      <th>Норма расхода</th>
                      {canEdit && <th>Действия</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredCovers.length === 0 ? (
                      <tr>
                        <td colSpan={canEdit ? 7 : 6} className="db-empty">
                          {covers.length === 0 ? 'Нет данных' : 'Ничего не найдено по запросу'}
                        </td>
                      </tr>
                    ) : (
                      filteredCovers.map((row, idx) => (
                        <tr key={row.id}>
                          <td>{idx + 1}</td>
                          <td>{row.decimal_code ?? '—'}</td>
                          <td>{row.classifier_description ?? '—'}</td>
                          <td>{row.for_body ?? '—'}</td>
                          <td>
                            {canEdit ? (
                              <input
                                type="number"
                                step="any"
                                value={row.cover_cost ?? ''}
                                onChange={(e) => updateCoverField(row.id, 'cover_cost', e.target.value)}
                                className="db-input db-input-num"
                              />
                            ) : (
                              row.cover_cost != null ? row.cover_cost : '—'
                            )}
                          </td>
                          <td>
                            {canEdit ? (
                              <input
                                type="number"
                                step="any"
                                value={row.run_norm ?? ''}
                                onChange={(e) => updateCoverField(row.id, 'run_norm', e.target.value)}
                                className="db-input db-input-num"
                              />
                            ) : (
                              row.run_norm != null ? row.run_norm : '—'
                            )}
                          </td>
                          {canEdit && (
                            <td>
                              <button
                                type="button"
                                className="db-save-btn"
                                onClick={() => handleSaveCover(row)}
                                disabled={savingId === row.id}
                              >
                                {savingId === row.id ? '...' : 'Сохранить'}
                              </button>
                            </td>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === 'works' && (
          <div className="db-section db-works-section">
            {loading ? (
              <p className="db-loading">Загрузка...</p>
            ) : (
              <div className="db-table-wrapper">
                <table className="db-table db-table-works">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th className="col-works-name">Наименование</th>
                      <th>Тип работы</th>
                      <th>Категория</th>
                      <th className="col-works-multiline">Трудоёмкость,<br />н/час</th>
                      <th className="col-works-multiline">Стоимость<br />н/час (руб.)</th>
                      <th className="col-works-multiline col-works-basewage">Основная ЗП<br />(руб.)</th>
                      <th>Активна</th>
                      {canEditWorks && <th>Действия</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredWorks.length === 0 ? (
                      <tr>
                        <td colSpan={canEditWorks ? 9 : 8} className="db-empty">
                          {works.length === 0 ? 'Нет данных' : 'Ничего не найдено по запросу'}
                        </td>
                      </tr>
                    ) : (
                      filteredWorks.map((row) => (
                        <tr key={row.id}>
                          <td>{row.id}</td>
                          <td className="col-works-name">{row.наименование ?? '—'}</td>
                          <td>{row.тип_работы ?? '—'}</td>
                          <td>{row.категория ?? '—'}</td>
                          <td>{row.labor_hours != null ? Number(row.labor_hours) : '—'}</td>
                          <td>{row.hour_rate != null ? Number(row.hour_rate).toFixed(2) : '—'}</td>
                          <td className="col-works-basewage">{row.base_wage != null ? Number(row.base_wage).toFixed(2) : '—'}</td>
                          <td>{row.активна == null ? '—' : row.активна ? 'Да' : 'Нет'}</td>
                          {canEditWorks && (
                            <td className="db-actions-cell">
                              <span className="db-actions-inner">
                                <button
                                  type="button"
                                  className="db-work-btn db-work-btn-edit"
                                  onClick={() => openWorkCard(row)}
                                >
                                  Изменить
                                </button>
                                <button
                                  type="button"
                                  className="db-work-btn db-work-btn-delete"
                                  onClick={() => handleDeleteWork(row.id)}
                                  disabled={deletingWorkId === row.id}
                                >
                                  {deletingWorkId === row.id ? '…' : 'Удалить'}
                                </button>
                              </span>
                            </td>
                          )}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {editingWork && (
          <div className="db-modal-overlay" onClick={() => setEditingWork(null)}>
            <div className="db-modal db-work-card" onClick={(e) => e.stopPropagation()}>
              <h3 className="db-modal-title">Карточка вида работ</h3>
              <div className="db-modal-body">
                <div className="db-form-group">
                  <label>Наименование *</label>
                  <input
                    type="text"
                    value={editingWork.наименование}
                    onChange={(e) => setEditingWork({ ...editingWork, наименование: e.target.value })}
                    className="db-input"
                    placeholder="Наименование работы"
                  />
                </div>
                <div className="db-form-group">
                  <label>Тип работ</label>
                  <input
                    type="text"
                    value={editingWork.тип_работы}
                    onChange={(e) => setEditingWork({ ...editingWork, тип_работы: e.target.value })}
                    className="db-input"
                    placeholder="Тип работы"
                  />
                </div>
                <div className="db-form-group">
                  <label>Категория</label>
                  <input
                    type="text"
                    value={editingWork.категория}
                    onChange={(e) => setEditingWork({ ...editingWork, категория: e.target.value })}
                    className="db-input"
                    placeholder="Категория"
                  />
                </div>
                <div className="db-form-group">
                  <label>Трудоёмкость, н/час</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={editingWork.labor_hours}
                    onChange={(e) => setEditingWork({ ...editingWork, labor_hours: e.target.value })}
                    className="db-input db-input-num"
                    placeholder="0"
                  />
                </div>
                <div className="db-form-group">
                  <label>Стоимость н/час (руб.)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editingWork.hour_rate}
                    onChange={(e) => setEditingWork({ ...editingWork, hour_rate: e.target.value })}
                    className="db-input db-input-num"
                    placeholder="0"
                  />
                </div>
                <div className="db-form-group">
                  <label>Основная ЗП (руб.)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editingWork.base_wage}
                    onChange={(e) => setEditingWork({ ...editingWork, base_wage: e.target.value })}
                    className="db-input db-input-num"
                    placeholder="0"
                  />
                </div>
                <div className="db-form-group">
                  <label>
                    <input
                      type="checkbox"
                      checked={editingWork.активна}
                      onChange={(e) => setEditingWork({ ...editingWork, активна: e.target.checked })}
                    />
                    {' '}Активна
                  </label>
                </div>
              </div>
              <div className="db-modal-footer">
                <button type="button" className="db-cancel-btn" onClick={() => setEditingWork(null)}>
                  Отмена
                </button>
                <button type="button" className="db-save-btn" onClick={handleUpdateWork}>
                  Сохранить
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default Database
