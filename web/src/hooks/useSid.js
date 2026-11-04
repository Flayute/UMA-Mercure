// Sesión del dispositivo: por defecto todos comparten 'main'.
// setSid() guarda la sesión propia tras un fork; apiUrl() añade ?sid= a todo.
export function getSid() {
  return localStorage.getItem('uma-sid') || 'main'
}

export function setSid(sid) {
  if (!sid || sid === 'main') localStorage.removeItem('uma-sid')
  else localStorage.setItem('uma-sid', sid)
}

export function apiUrl(path) {
  const sid = getSid()
  return path + (path.includes('?') ? '&' : '?') + 'sid=' + encodeURIComponent(sid)
}
