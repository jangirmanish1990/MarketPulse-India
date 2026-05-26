import { createContext, useContext, useState, useCallback } from "react"
import axios from "axios"

const API = ""
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const login = useCallback(async (email, password) => {
    setLoading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append("username", email)
      form.append("password", password)
      const res = await axios.post(`${API}/api/auth/login`, form)
      const { access_token } = res.data
      setToken(access_token)

      // Fetch user info
      const me = await axios.get(`${API}/api/auth/me`, {
        headers: { Authorization: `Bearer ${access_token}` },
      })
      setUser(me.data)
      return true
    } catch (e) {
      setError(e.response?.data?.message || "Login failed")
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
  }, [])

  // Returns an axios config object with the Bearer header pre-populated.
  // Usage: axios.get(url, authAxios()) or axios.post(url, body, authAxios())
  const authAxios = useCallback(
    (config = {}) => ({
      ...config,
      headers: {
        ...config.headers,
        Authorization: `Bearer ${token}`,
      },
    }),
    [token]
  )

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        loading,
        error,
        login,
        logout,
        authAxios,
        isAuthenticated: !!token,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
