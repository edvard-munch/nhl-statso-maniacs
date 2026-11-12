import type { RegistrationCredentialsRequest } from '../../src/api/index.js';

export function registration(
  overrides: Partial<RegistrationCredentialsRequest> = {},
): RegistrationCredentialsRequest {
  return {
    username: 'new-user',
    email: 'reused@example.invalid',
    password1: '  exact chosen password  ',
    password2: '  exact chosen password  ',
    ...overrides,
  };
}
