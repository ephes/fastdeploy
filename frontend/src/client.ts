import { ref } from 'vue';

class Client {
  name = 'websocket client..';
  connection: any;
  messages: any;
  access_token: string = ''

  constructor() {
    this.messages = ref([]);
    this.initWebsocketConnection()
  }

  initWebsocketConnection() {
    //document.cookie = 'auth=' + this.access_token + '; path="/deployments"'
    this.connection = new WebSocket('ws://localhost:8000/deployments/ws/1');
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
    const headers = {'authorization': `Bearer ${this.access_token}`}
    fetch("http://localhost:8000/deployments/deploy", { method: 'POST' , headers: headers})
      .then(response => response.json())
      .then(data => console.log("fetch response: ", data))
  }
}

export default Client;
