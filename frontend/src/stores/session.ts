import { useAuth } from "./auth";

/**
 * Remember the login session a request was started in.
 *
 * Call this before awaiting a response and ask the returned function
 * afterwards: it answers false once the user was logged out (or logged
 * in again) in the meantime. A response that arrives then belongs to a
 * session that is over and must not be written into a store.
 *
 * @returns isCurrent {() => boolean} whether the session is still the same
 */
export function rememberSession(): () => boolean {
  const auth = useAuth();
  const sessionId = auth.sessionId;
  return () => auth.sessionId === sessionId;
}
