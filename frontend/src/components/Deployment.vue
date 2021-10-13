<script setup lang="ts">
import { ref } from "vue";

function toMessage(message: string) {
  return { message: message };
}

const inner: any[] = [];
const messages = ref(inner);
// const messages = ref(['foo', 'bar', 'baz'].map(toMessage));
console.log("messages: ", messages);

const connection = new WebSocket("ws://localhost:8000/ws/1");
connection.onmessage = function (event) {
  const message = JSON.parse(event.data);
  console.log(message);
  messages.value.push(message);
};

connection.onopen = function (event) {
  console.log(event);
  console.log("Successfully connected to the echo websocket server...");
};

function sendMessage() {
  console.log("trying to send message");
  connection.send(JSON.stringify({ message: "message from client!" }));
}

fetch("http://localhost:8000/")
  .then((response) => response.json())
  .then((data) => console.log("fetch: ", data));
</script>

<template>
  <div>
    <h1>View deployment</h1>
    <p>Some paragraph..</p>
    <button type="button" @click="sendMessage()">send message</button>
    <ul id="messages">
      <li v-for="message in messages" :key="message.message">
        {{ message.message }}
      </li>
    </ul>
  </div>
</template>
