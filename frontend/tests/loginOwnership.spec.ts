import { vi } from "vitest";
import { initPinia } from "./conftest";
import { useAuth } from "../src/stores/auth";

function deferred() {
  let resolve!: (value: any) => void;
  let reject!: (error: any) => void;
  const promise = new Promise<any>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function attemptSetup() {
  initPinia();
  const auth = useAuth();
  const a = deferred(), b = deferred();
  const post = vi.fn().mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
  const client = { post, options: { headers: {} } };
  auth.client = client as any;
  auth.username = "sample";
  auth.password = "first-password";
  auth.onLoginSuccess = vi.fn();
  return { auth, a, b, client };
}
function settle(request: ReturnType<typeof deferred>, success: boolean, token: string) {
  if (success) request.resolve({ access_token: token });
  else request.reject({ response: { status: 401 } });
}

it.each([true, false])("older success cannot replace newer result (newer success: %s)", async success => {
  const { auth, a, b, client } = attemptSetup();
  const first = auth.login();
  auth.password = "second-password";
  const second = auth.login();
  settle(b, success, "newer");
  await second;
  const token = auth.accessToken, error = auth.errorMessage, password = auth.password;
  a.resolve({ access_token: "stale" });
  await first;
  expect(auth.accessToken).toBe(token);
  expect(auth.errorMessage).toBe(error);
  expect(auth.password).toBe(password);
  expect(client.options).not.toHaveProperty("body");
  expect(auth.client.options).not.toHaveProperty("body");
  expect(auth.accessToken).toBe(success ? "newer" : null);
});

it.each([true, false])("older completion leaves pending newer request private (success: %s)", async success => {
  const { auth, a, b, client } = attemptSetup();
  const first = auth.login();
  auth.password = "second-password";
  const second = auth.login();
  settle(a, success, "stale");
  await first;
  expect(auth.accessToken).toBe(null);
  expect(auth.errorMessage).toBe(null);
  expect(auth.password).toBe("second-password");
  expect(client.options).not.toHaveProperty("body");
  expect(client.options.headers).not.toHaveProperty("Content-Type");
  b.resolve({ access_token: "newer" });
  await second;
  expect(auth.accessToken).toBe("newer");
  expect(auth.password).toBe("");
});

it.each(["logout", "empty submission"])("invalidates pending attempts on %s", async action => {
  const { auth, a } = attemptSetup();
  const first = auth.login();
  if (action === "logout") auth.logout();
  else { auth.password = ""; await auth.login(); }
  const error = auth.errorMessage;
  a.resolve({ access_token: "stale" });
  await first;
  expect(auth.accessToken).toBe(null);
  expect(auth.errorMessage).toBe(error);
});
