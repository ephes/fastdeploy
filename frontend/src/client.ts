import { ref } from 'vue';

class Client {
  name = 'websocket client..';
  connection: any;
  messages: any;
  access_token: string = '';
  is_authenticated: any;

  constructor() {
    this.messages = ref([]);
    this.is_authenticated = ref(false)
    this.initWebsocketConnection();
  }

  initWebsocketConnection() {
    //document.cookie = 'auth=' + this.access_token + '; path="/deployments"'
    this.connection = new WebSocket('ws://localhost:8000/deployments/ws/1');
    this.connection.onopen = (event: MessageEvent) => {
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
  startDeployment() {
    const headers = { authorization: `Bearer ${this.access_token}` };
    fetch('http://localhost:8000/deployments/deploy', {
      method: 'POST',
      headers: headers,
    })
      .then((response) => response.json())
      .then((data) => console.log('fetch response: ', data));
  }
  login = async (username: string, password: string) => {
    let formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    const response = await fetch('http://localhost:8000/token', {
      method: 'POST',
      body: formData,
    })
    const result = await response.json()
    console.log('username, password: ', username, password);
    console.log('returned data: ', result)
    this.access_token = result.access_token
    this.is_authenticated.value = true;
  }
}

export default Client;
