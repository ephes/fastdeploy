import { v4 as uuidv4 } from "uuid";
import { pythonToJavascript } from "./converters";
import { WebsocketClient, Message, AuthenticationMessage, WarningMessage } from "./typings";
import { useWebsocketStore } from "./stores/websocket";
import { useAuth } from "./stores/auth";
import { useServices } from "./stores/service";
import { useDeployments } from "./stores/deployment";
import { useSteps } from "./stores/step";
import { rememberSession } from "./stores/session";
import { readStrictJson } from "./strictJson";
import { isId as id, isOptionalDeleted, isOptionalWireDate as optionalDate, isRecord as isWireRecord, isStepState, isWireDate as date } from "./wireValues";

// The message switch reads several optional fields; REST admission keeps the stricter `unknown` view.
const isRecord = isWireRecord as (value: unknown) => value is Record<string, any>;

const MAX_PARALLEL_STEP_REFRESHES = 4;
const CONNECTION_OPEN_DEADLINE_MS = 15_000;
const AUTHENTICATION_DEADLINE_MS = 15_000;
const MAX_SERVER_WARNING_LENGTH = 256;

const readyState: { [key: number]: string } = {
  0: "CONNECTING",
  1: "OPEN",
  2: "CLOSING",
  3: "CLOSED",
};

// Only declared domain fields enter the generic case/date converters. Extra
// wire keys could shadow Object methods or be mistaken for date properties.
const domainFields: Record<string, string[]> = {
  service: ["type", "id", "name", "data", "deleted"],
  deployment: ["type", "id", "service_id", "origin", "user", "started", "finished", "context", "deleted"],
  step: ["type", "id", "deployment_id", "name", "state", "message", "started", "finished", "deleted"],
  user: ["type", "id", "name"],
};

// Validate the wire representation before date conversion or store dispatch.
function validMessage(value: unknown): value is Message {
  if (!isRecord(value)) return false;
  if (!isOptionalDeleted(value.deleted)) return false;
  switch (value.type) {
    case "authentication":
      return ["success", "failure"].includes(value.status) &&
        (value.detail == null || typeof value.detail === "string");
    case "service":
      return id(value.id) && typeof value.name === "string" && isRecord(value.data);
    case "deployment":
      return id(value.id) && id(value.service_id) && typeof value.origin === "string" &&
        typeof value.user === "string" && date(value.started) && optionalDate(value.finished);
    case "step":
      return id(value.id) && id(value.deployment_id) && typeof value.name === "string" &&
        isStepState(value.state) &&
        typeof value.message === "string" && optionalDate(value.started) && optionalDate(value.finished);
    case "user":
      return id(value.id) && typeof value.name === "string";
    case "warning":
      return typeof value.detail === "string";
    default:
      // Existing endpoint's informational control messages have no type.
      return value.type === undefined && typeof value.message === "string";
  }
}

export function createWebsocketClient(): WebsocketClient {
  /**
   * Create a websocket client
   */
  let generation = 0;
  let authenticatedGeneration = -1;
  let hasAuthenticated = false;
  let handshakeDeadline: ReturnType<typeof setTimeout> | undefined;
  function clearHandshakeDeadline() {
    clearTimeout(handshakeDeadline);
    handshakeDeadline = undefined;
  }

  // In-flight inventories retain their slots across socket replacements until they settle.
  const stepRefreshes = new Set<Promise<void>>();
  const client: WebsocketClient = {
    /**
     * The websocket client id which is used to identify the websocket client
     * by the server.
     *
     */
    uuid: uuidv4(),
    /**
     * List of all stores which should be notified when messages are received.
     */
    stores: [],
    /**
     * Count the number of connection attempts since last successful connection.
     */
    retryCount: 0,
    /**
     * Set by dispose(). A disposed client never connects, reconnects,
     * authenticates or passes on a message again.
     */
    disposed: false,
    /**
     * End this client for good: called on logout. Detaches the event
     * handlers before closing, so the close does not start the
     * reconnect loop, and a reconnect timer that is already waiting
     * finds the client disposed. The stores are dropped so no late
     * message can reach them.
     */
    dispose() {
      this.disposed = true;
      clearHandshakeDeadline();
      this.stores = [];
      const connection = this.connection;
      if (connection !== undefined) {
        connection.onclose = null;
        connection.onopen = null;
        connection.onmessage = null;
        try {
          connection.close();
        } catch (err) {
          console.log("closing websocket failed: ", err);
        }
      }
    },
    /**
     * Register a store to be notified when a message is received.
     *
     * @param store
     */
    registerStore(store: any) {
      this.stores.push(store);
    },
    /**
     * Callback for when the websocket is opened. Passes information
     * about connection state to websocketStore and calls a method
     * to authenticate the websocket connection.
     *
     * @param accessToken {string}
     * @param event {Event}
     */
    onConnectionOpen(accessToken: string, event: Event) {
      if (this.disposed) {
        // opened after logout: do not send the old token, just hang up
        const lateConnection = event.target as WebSocket | null;
        if (lateConnection && typeof lateConnection.close === "function") {
          lateConnection.close();
        }
        return;
      }
      console.log("Successfully connected to the echo websocket server..");
      const websocketStore = useWebsocketStore();
      websocketStore.handling = "on open";
      const connection: WebSocket = event.target as WebSocket;
      if (connection !== undefined) {
        websocketStore.connection = readyState[connection.readyState];
        this.authenticateWebsocketConnection(connection, accessToken);
      }
    },
    /**
     * React to the websocket connection being closed. This
     * usually happens when the server is restarted.
     *
     * @param accessToken {string} The access token to use for authentication
     * @param event {CloseEvent} The close event
     */
    onConnectionClose(accessToken: string, websocketUrl: string, _event: CloseEvent) {
      return closeAndReconnect(websocketUrl, accessToken);
    },
    /**
     * Pass message to the different stores.
     *
     * @param message {Message} The message to pass to the stores
     */
    notifyStores(message: Message) {
      if (this.disposed) {
        return;
      }
      const newMessage = pythonToJavascript(message);
      let deliveryFailed = false;
      for (const store of this.stores) {
        if (this.disposed) return;
        try {
          store.onMessage(newMessage);
        } catch {
          deliveryFailed = true;
        }
      }
      if (deliveryFailed && !this.disposed) {
        // Reconnect refreshes cover a bounded subset of state. Keep the alert
        // until the user refreshes the page or the session resets.
        console.warn("Websocket store failed to apply a live update; refresh to resynchronize.");
        useWebsocketStore().resyncError = "A live update could not be applied. Refresh to resynchronize.";
      }
    },
    /**
     * Handle received authentication message from the server.
     * It's either a success or failure response.
     *
     * @param authenticationMessage: {AuthenticationMessage} The authentication message received from the server
     */
    onAuthenticationMessage(authenticationMessage: AuthenticationMessage) {
      clearHandshakeDeadline();
      const websocketStore = useWebsocketStore();
      if (authenticationMessage.status === "success") {
        websocketStore.handling = "on authentication message";
        websocketStore.authentication = "authenticated";
        this.retryCount = 0; // reset retry count for next onConnectionClose event
        if (authenticatedGeneration !== generation) {
          authenticatedGeneration = generation;
          websocketStore.serverWarning = "";
          const reconnect = hasAuthenticated;
          hasAuthenticated = true;
          if (reconnect) {
            const refreshGeneration = generation;
            const isCurrentSession = rememberSession();
            const ownsRefresh = () => !this.disposed && generation === refreshGeneration && isCurrentSession();
            const services = useServices(), deployments = useDeployments(), steps = useSteps();
            // Revisit only the already visible number of pages, never drain history.
            const pages = Math.max(1, Math.ceil(deployments.historyIds.length / 50));
            const serviceId = deployments.historyServiceId;
            const refreshHistory = async () => {
              const firstPage = deployments.fetchDeployments(serviceId, false, ownsRefresh);
              const historyGeneration = deployments.historyGeneration;
              await firstPage;
              for (let page = 1; page < pages && ownsRefresh() && deployments.historyGeneration === historyGeneration
                  && deployments.historyHasMore && !deployments.historyError; page++) {
                await deployments.fetchDeployments(serviceId, true, ownsRefresh);
              }
            };
            const relevant = new Set([...Object.keys(steps.stepsByDeployment), ...Object.keys(steps.fetchGenerations)]);
            const refreshSteps = async () => {
              for (const id of relevant) {
                if (stepRefreshes.size >= MAX_PARALLEL_STEP_REFRESHES) await Promise.race(stepRefreshes);
                if (!ownsRefresh()) return;
                const refresh = steps.fetchStepsFromDeployment(Number(id), ownsRefresh)
                  .catch(() => { /* Individual inventory failures must not stop the queue. */ })
                  .finally(() => { stepRefreshes.delete(refresh); });
                stepRefreshes.add(refresh);
              }
            };
            // Store actions retain event-touched ids; all failures are observed.
            void Promise.allSettled([
              services.fetchServices(ownsRefresh), services.fetchServiceNames(ownsRefresh), refreshHistory(),
              refreshSteps(),
            ]);
          }
        }
      } else {
        websocketStore.handling = "on authentication message";
        websocketStore.authentication = "authentication failure";
        const auth = useAuth();
        auth.logout();
      }
    },
    /**
     * All messages received from the websocket server are passed to this
     * method and eventually dispatched to the stores.
     *
     * @param event {MessageEvent} The url of the websocket server
     */
    onMessage(event: MessageEvent) {
      if (this.disposed) {
        return;
      }
      let message: any;
      try {
        if (typeof event.data !== "string") throw new Error();
        message = readStrictJson(event.data);
        if (!validMessage(message)) throw new Error();
      } catch {
        // Retire queued callbacks as well as installed handlers. Recovery is an
        // explicit refresh, avoiding a reconnect loop on a broken protocol.
        generation++;
        clearHandshakeDeadline();
        const connection = this.connection;
        if (connection) {
          connection.onopen = connection.onclose = connection.onmessage = null;
          try { connection.close(); } catch { /* Already unavailable. */ }
        }
        useWebsocketStore().protocolError = "Invalid websocket message; refresh to resynchronize.";
        useWebsocketStore().handling = useWebsocketStore().protocolError;
        useWebsocketStore().connection = "CLOSED";
        useWebsocketStore().authentication = "not authenticated";
        console.warn("Invalid websocket message; refresh to resynchronize.");
        return;
      }
      if (!("type" in message)) return;
      if (message.type !== "authentication" && authenticatedGeneration !== generation) return;
      if (message.type === "warning") {
        const warning = message as WarningMessage;
        useWebsocketStore().serverWarning = warning.detail.slice(0, MAX_SERVER_WARNING_LENGTH);
        return;
      }
      useWebsocketStore().receivedMessage();
      if (message.type === "authentication") {
        // special handling for authentication response
        this.onAuthenticationMessage(message as AuthenticationMessage);
      } else {
        const fields = domainFields[message.type as string];
        const domainMessage = Object.fromEntries(
          Object.entries(message).filter(([key]) => fields.includes(key))
        );
        this.notifyStores(domainMessage as Message);
      }
    },
    /**
     * Initialize the websocket connection. This is called when a websocket
     * connection should be established.
     *
     * @param websocketUrl {string} The url of the websocket server
     * @param accessToken {string} The access token to use for authentication
     */
    initWebsocketConnection(websocketUrl: string, accessToken: string) {
      if (this.disposed) {
        return;
      }
      clearHandshakeDeadline();
      // create the websocket connection
      const websocketStore = useWebsocketStore();
      websocketStore.protocolError = "";
      websocketStore.connectionError = "";
      websocketStore.handling = "init connection";
      websocketStore.authentication = "not authenticated";
      const currentGeneration = ++generation;
      const previous = this.connection;
      this.connection = undefined;
      if (previous) {
        previous.onclose = previous.onopen = previous.onmessage = null;
        previous.close();
      }
      try {
        this.connection = new WebSocket(`${websocketUrl}/${this.uuid}`);
      } catch {
        websocketStore.connection = "CLOSED";
        websocketStore.connectionError = "Unable to open websocket; refresh to try again.";
        websocketStore.handling = websocketStore.connectionError;
        return;
      }
      websocketStore.connection = readyState[this.connection.readyState];
      console.log("connecting to websocket: ", this.connection);

      // register event listeners for the websocket connection
      const isCurrent = () => !this.disposed && generation === currentGeneration;
      this.connection.onclose = (event) => {
        if (isCurrent()) return this.onConnectionClose(accessToken, websocketUrl, event);
      };
      this.connection.onopen = (event) => {
        if (!isCurrent()) return;
        clearHandshakeDeadline();
        try {
          this.onConnectionOpen(accessToken, event);
        } catch {
          void closeAndReconnect(websocketUrl, accessToken, "Unable to send websocket credentials.");
          return;
        }
        handshakeDeadline = setTimeout(() => {
          if (isCurrent()) {
            void closeAndReconnect(websocketUrl, accessToken, "Websocket authentication timed out.");
          }
        }, AUTHENTICATION_DEADLINE_MS);
      };
      this.connection.onmessage = (event) => {
        if (isCurrent()) this.onMessage(event);
      };
      handshakeDeadline = setTimeout(() => {
        if (isCurrent()) {
          void closeAndReconnect(websocketUrl, accessToken, "Websocket connection timed out.");
        }
      }, CONNECTION_OPEN_DEADLINE_MS);
    },
    /**
     * Send access token as message (json string) to the websocket server.
     *
     * @param connection {WebSocket} The websocket connection
     * @param accessToken {string} The access token to use for authentication
     */
    authenticateWebsocketConnection(connection: any, accessToken: string) {
      const credentials = JSON.stringify({ access_token: accessToken });
      connection.send(credentials);
      const websocketStore = useWebsocketStore();
      websocketStore.handling = "send credentials";
      websocketStore.authentication = "authenticating...";
    },
  };

  async function closeAndReconnect(websocketUrl: string, accessToken: string, error?: string) {
    const connection = client.connection;
    if (!connection || client.disposed) return;

    // Retire the socket before closing it so queued events cannot use the session.
    const closingGeneration = ++generation;
    clearHandshakeDeadline();
    client.connection = undefined;
    connection.onclose = connection.onopen = connection.onmessage = null;
    const websocketStore = useWebsocketStore();
    websocketStore.connection = "CLOSED";
    websocketStore.authentication = "not authenticated";
    websocketStore.handling = error ?? "on close";
    if (error) {
      websocketStore.connectionError = error;
      console.warn(error);
      try { connection.close(); } catch { /* The socket has already been retired. */ }
    }

    if (client.retryCount >= 3) {
      websocketStore.connectionError = "Websocket reconnect attempts exhausted. Refresh to try again.";
      websocketStore.handling = websocketStore.connectionError;
      return;
    }
    client.retryCount++;
    await new Promise((resolve) => setTimeout(resolve, 1000));
    if (client.disposed || generation !== closingGeneration) return;
    console.log("Attempting to reconnect to websocket server: ", client.retryCount);
    client.initWebsocketConnection(websocketUrl, accessToken);
  }

  return client;
}
