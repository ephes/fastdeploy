import { ref } from 'vue';

class Client {
  name = 'websocket client..';
  connection: any;
  messages: any;

  constructor() {
    this.messages = ref([]);
    this.connection = new WebSocket('ws://localhost:8000/ws/1');
    this.connection.onopen = function (event: MessageEvent) {
      console.log(event);
      console.log('Successfully connected to the echo websocket server...');
    };

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
}

export default Client;
