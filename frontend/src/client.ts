import { ref } from 'vue';

class Client {
  name = 'websocket client..';
  connection: any;
  messages: any;

  constructor() {
    this.messages = ref([]);
    this.initWebsocketConnection()
  }

  initWebsocketConnection() {
    this.connection = new WebSocket('ws://localhost:8000/ws/1');
    this.connection.onopen = (event: MessageEvent) => {
      console.log(event);
      console.log('Successfully connected to the echo websocket server...');
    }
    this.connection.onmessage = (event: MessageEvent) => {
      const message = JSON.parse(event.data);
      console.log('in client.ts: ', message);
      this.messages.value.push(message);
    };

  }
  sendMessage() {
    this.connection.send(
      JSON.stringify({ message: 'message from client client!' })
    );
  }
  startDeployment() {
    fetch("http://localhost:8000/deploy", { method: 'POST' })
      .then(response => response.json())
      .then(data => console.log("fetch response: ", data))
  }
}

export default Client;
