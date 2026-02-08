import axios from "axios";

const apiClient = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
});

export function setAuthHeaders(companyId: string, userId: string, role: string) {
  apiClient.defaults.headers.common["X-Company-Id"] = companyId;
  apiClient.defaults.headers.common["X-User-Id"] = userId;
  apiClient.defaults.headers.common["X-Role"] = role;
}

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error) && error.response?.data?.detail) {
    return String(error.response.data.detail);
  }
  if (axios.isAxiosError(error) && error.response?.data?.error) {
    return String(error.response.data.error);
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "An unexpected error occurred";
}

export { apiClient };
