import { vi } from "vitest";
import { initPinia } from "./conftest";
import { useAuth } from "../src/stores/auth";

describe("Auth Store Actions", () => {
  beforeEach(() => {
    initPinia();
  });

  it("returns early if username or password are not set", async () => {
    const authStore = useAuth();
    authStore.username = "user";
    authStore.password = "";
    expect(authStore.errorMessage).toBe(null);
    await authStore.login();
    expect(authStore.errorMessage).toBe("Please enter a username and password");
  });

  it("calls login with error", async () => {
    const authStore = useAuth();
    authStore.username = "user";
    authStore.password = "password";
    authStore.client = {
      async post<T = unknown>(): Promise<T> {
        return new Promise<any>(() => {
          throw Error("Incorrect username or password")
        });
      },
      options: {headers: {}},
    } as any;
    expect(authStore.errorMessage).toBe(null);
    await authStore.login();
    expect(authStore.errorMessage).toBe("Incorrect username or password");
  });

  it("calls login successfully", async () => {
    const authStore = useAuth();
    authStore.username = "user";
    authStore.password = "password";
    authStore.client = {
      async post<T = unknown>(): Promise<T> {
        return new Promise<any>((resolve, reject) => {
          resolve({access_token: "access_token"});
        });
      },
      options: {headers: {}},
    } as any;
    authStore.onLoginSuccess = vi.fn();  // mock onLoginSuccess action
    expect(authStore.isAuthenticated).toBe(false);
    await authStore.login();
    expect(authStore.isAuthenticated).toBe(true);
  });
});
