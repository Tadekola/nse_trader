/**
 * Centralized API Client
 * 
 * Provides:
 * - Consistent error handling
 * - Request/response logging (dev only)
 * - Timeouts
 * - Retry logic for transient failures
 * - Type-safe responses
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const DEFAULT_TIMEOUT = 15000;
const MAX_RETRIES = 2;
const RETRY_DELAY = 1000;

const isDev = import.meta.env.DEV;

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public endpoint: string,
    public details?: unknown
  ) {
    super(`API Error ${status}: ${statusText} at ${endpoint}`);
    this.name = 'ApiError';
  }
}

export class NetworkError extends Error {
  constructor(public endpoint: string, public originalError: Error) {
    super(`Network error at ${endpoint}: ${originalError.message}`);
    this.name = 'NetworkError';
  }
}

export class TimeoutError extends Error {
  constructor(public endpoint: string, public timeoutMs: number) {
    super(`Request timed out after ${timeoutMs}ms at ${endpoint}`);
    this.name = 'TimeoutError';
  }
}

interface RequestOptions extends RequestInit {
  timeout?: number;
  retries?: number;
  skipLogging?: boolean;
}

function log(level: 'info' | 'warn' | 'error', message: string, data?: unknown) {
  if (!isDev) return;
  
  const timestamp = new Date().toISOString().split('T')[1].slice(0, 12);
  const prefix = `[API ${timestamp}]`;
  
  switch (level) {
    case 'info':
      console.log(`${prefix} ${message}`, data ?? '');
      break;
    case 'warn':
      console.warn(`${prefix} ${message}`, data ?? '');
      break;
    case 'error':
      console.error(`${prefix} ${message}`, data ?? '');
      break;
  }
}

async function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    return response;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function apiRequest<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const {
    timeout = DEFAULT_TIMEOUT,
    retries = MAX_RETRIES,
    skipLogging = false,
    ...fetchOptions
  } = options;

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  const method = fetchOptions.method || 'GET';
  
  if (!skipLogging) {
    log('info', `${method} ${endpoint}`);
  }

  let lastError: Error | null = null;
  
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetchWithTimeout(url, {
        ...fetchOptions,
        headers: {
          'Content-Type': 'application/json',
          ...fetchOptions.headers,
        },
      }, timeout);

      if (!response.ok) {
        let details: unknown;
        try {
          details = await response.json();
        } catch {
          details = await response.text();
        }
        
        log('error', `${method} ${endpoint} failed: ${response.status}`, details);
        throw new ApiError(response.status, response.statusText, endpoint, details);
      }

      const data = await response.json();
      
      if (!skipLogging) {
        log('info', `${method} ${endpoint} OK`, { 
          dataKeys: typeof data === 'object' && data ? Object.keys(data) : typeof data 
        });
      }
      
      return data as T;
      
    } catch (error) {
      if (error instanceof ApiError) {
        // Don't retry client errors (4xx)
        if (error.status >= 400 && error.status < 500) {
          throw error;
        }
      }
      
      if (error instanceof Error && error.name === 'AbortError') {
        lastError = new TimeoutError(endpoint, timeout);
      } else if (error instanceof ApiError) {
        lastError = error;
      } else if (error instanceof Error) {
        lastError = new NetworkError(endpoint, error);
      } else {
        lastError = new Error(`Unknown error at ${endpoint}`);
      }
      
      if (attempt < retries) {
        const delayMs = RETRY_DELAY * Math.pow(2, attempt);
        log('warn', `${method} ${endpoint} failed, retrying in ${delayMs}ms (attempt ${attempt + 1}/${retries})`);
        await delay(delayMs);
      }
    }
  }

  log('error', `${method} ${endpoint} failed after ${retries + 1} attempts`, lastError);
  throw lastError;
}

// Convenience methods
export const api = {
  get: <T>(endpoint: string, options?: RequestOptions) => 
    apiRequest<T>(endpoint, { ...options, method: 'GET' }),
    
  post: <T>(endpoint: string, body: unknown, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { 
      ...options, 
      method: 'POST',
      body: JSON.stringify(body),
    }),
    
  put: <T>(endpoint: string, body: unknown, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { 
      ...options, 
      method: 'PUT',
      body: JSON.stringify(body),
    }),
    
  delete: <T>(endpoint: string, options?: RequestOptions) =>
    apiRequest<T>(endpoint, { ...options, method: 'DELETE' }),
};

export { API_BASE_URL };
