import { createContext, useEffect, useState, type ReactNode } from "react";
import { setAuthHeaders } from "@/lib/api/client";

interface AuthContextValue {
  companyId: string;
  userId: string;
  role: string;
  setCompanyId: (companyId: string) => void;
  setUserId: (userId: string) => void;
  setRole: (role: string) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

const DEFAULT_COMPANY_ID = "00000000-0000-0000-0000-000000000001";
const DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001";
const DEFAULT_ROLE = "admin";

function loadStored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [companyId, setCompanyId] = useState(() => loadStored("pto_company_id", DEFAULT_COMPANY_ID));
  const [userId, setUserId] = useState(() => loadStored("pto_user_id", DEFAULT_USER_ID));
  const [role, setRole] = useState(() => loadStored("pto_role", DEFAULT_ROLE));

  useEffect(() => {
    localStorage.setItem("pto_company_id", companyId);
    localStorage.setItem("pto_user_id", userId);
    localStorage.setItem("pto_role", role);
    setAuthHeaders(companyId, userId, role);
  }, [companyId, userId, role]);

  return (
    <AuthContext.Provider
      value={{
        companyId,
        userId,
        role,
        setCompanyId,
        setUserId,
        setRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
