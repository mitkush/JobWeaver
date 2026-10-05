# Google sign-in only in V1

Every JobWeaver User needs a Google account anyway: the Gmail Hand-off (ADR-0006) needs Gmail access, and in testing mode only named Google test users can use the OAuth app. Email-and-password sign-in would add email verification, password reset, a transactional email provider, password storage and extra rate limiting, all for an invite-only group whose members already sign in with Google. V1 therefore signs in with Google only, and the Admin's invite list is the same set of people added as Google test users.

**Considered and rejected:** Google plus email and password in V1 (extra security surface and a new provider for no current user), a third-party auth service (another free tier to depend on).

**Consequences:** no passwords are stored; email and password sign-in moves to Later and returns with the public launch gate (ADR-0012), where it is needed for users without Google accounts.
