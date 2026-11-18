
import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map, tap } from 'rxjs/operators';

export interface AuthUser {
  user_id: number;
  email: string;
  is_active: boolean;
  created_at: string;
}

interface LoginResponse {
  success: boolean;
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

interface ProfileResponse {
  success: boolean;
  user: AuthUser;
}

interface GuestSessionResponse {
  success: boolean;
  access_token: string;
  token_type: string;
  expires_in: number;
  guest_session_id: string;
  is_guest: boolean;
}

export interface RegisterResponse {
  success: boolean;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);

  private readonly tokenKey = 'datamind_access_token';
  private readonly guestTokenKey = 'datamind_guest_token';
  private readonly apiUrl = '';

  readonly currentUser = signal<AuthUser | null>(null);
  readonly isGuest = signal(false);

  getToken(): string | null {
    return localStorage.getItem(this.tokenKey)
      || sessionStorage.getItem(this.guestTokenKey);
  }

  getGuestToken(): string | null {
    return sessionStorage.getItem(this.guestTokenKey);
  }

  clearGuestToken(): void {
    sessionStorage.removeItem(this.guestTokenKey);
    this.isGuest.set(false);
  }

  startGuestSession(): Observable<GuestSessionResponse> {
    return this.http.post<GuestSessionResponse>(
      `${this.apiUrl}/api/auth/guest`,
      {},
    ).pipe(
      tap((response) => {
        sessionStorage.setItem(this.guestTokenKey, response.access_token);
        this.currentUser.set(null);
        this.isGuest.set(true);
      }),
    );
  }

  login(email: string, password: string): Observable<LoginResponse> {
    const body = new URLSearchParams();
    body.set('username', email);
    body.set('password', password);

    return this.http.post<LoginResponse>(
      `${this.apiUrl}/api/auth/login`,
      body.toString(),
      {
        headers: new HttpHeaders({
          'Content-Type': 'application/x-www-form-urlencoded',
        }),
      },
    ).pipe(
      tap((response) => {
        localStorage.setItem(this.tokenKey, response.access_token);
        this.currentUser.set(response.user);
        this.isGuest.set(false);
      }),
    );
  }

  register(email: string, password: string): Observable<RegisterResponse> {
    return this.http.post<RegisterResponse>(
      `${this.apiUrl}/api/auth/register`,
      { email, password },
    );
  }

  restoreSession(): Observable<AuthUser | null> {
    const userToken = localStorage.getItem(this.tokenKey);

    if (!userToken) {
      const guestToken = this.getGuestToken();
      this.isGuest.set(!!guestToken);
      this.currentUser.set(null);
      return of(null);
    }

    return this.http.get<ProfileResponse>(
      `${this.apiUrl}/api/auth/me`,
    ).pipe(
      tap((response) => {
        this.currentUser.set(response.user);
        this.isGuest.set(false);
      }),
      map((response) => response.user),
      catchError(() => {
        localStorage.removeItem(this.tokenKey);
        this.currentUser.set(null);

        const guestToken = this.getGuestToken();
        this.isGuest.set(!!guestToken);

        return of(null);
      }),
    );
  }

  logout(): void {
    localStorage.removeItem(this.tokenKey);
    sessionStorage.removeItem(this.guestTokenKey);

    this.currentUser.set(null);
    this.isGuest.set(false);
  }
}
