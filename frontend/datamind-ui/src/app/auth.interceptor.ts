import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthService } from './services/auth.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const authService = inject(AuthService);

  const publicEndpoints = [
    '/api/auth/login',
    '/api/auth/register',
    '/api/auth/guest',
  ];

  const isPublicEndpoint = publicEndpoints.some(
    (endpoint) => request.url.endsWith(endpoint),
  );

  if (isPublicEndpoint) {
    return next(request);
  }

  const token = authService.getToken();

  if (!token) {
    return next(request);
  }

  return next(request.clone({
    setHeaders: {
      Authorization: `Bearer ${token}`,
    },
  }));
};