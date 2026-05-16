import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet } from "react-native";
import { api } from "../api/client";

export default function ChatScreen() {
  const [msg, setMsg] = useState("");
  const [history, setHistory] = useState([]);

  const send = async () => {
    if (!msg.trim()) return;
    const userMsg = { role: "user", content: msg.trim() };
    setHistory((prev) => [...prev, userMsg]);
    setMsg("");
    try {
      const res = await api.chat(userMsg.content, history);
      setHistory((prev) => [...prev, { role: "assistant", content: res.reply || JSON.stringify(res) }]);
    } catch (e) {
      setHistory((prev) => [...prev, { role: "assistant", content: "Error: " + e.message }]);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView style={styles.messages}>
        {history.map((m, i) => (
          <View key={i} style={[styles.bubble, m.role === "user" ? styles.userBubble : styles.assistantBubble]}>
            <Text style={styles.bubbleText}>{m.content}</Text>
          </View>
        ))}
      </ScrollView>
      <View style={styles.inputRow}>
        <TextInput style={styles.input} value={msg} onChangeText={setMsg} placeholder="Type..." placeholderTextColor="#666" />
        <TouchableOpacity style={styles.sendBtn} onPress={send}><Text style={styles.sendText}>Send</Text></TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0a0a" },
  messages: { flex: 1, padding: 12 },
  bubble: { padding: 10, borderRadius: 8, marginVertical: 4, maxWidth: "80%" },
  userBubble: { backgroundColor: "#00ff88", alignSelf: "flex-end" },
  assistantBubble: { backgroundColor: "#1a1a1a", alignSelf: "flex-start", borderWidth: 1, borderColor: "#333" },
  bubbleText: { color: "#fff", fontSize: 14 },
  inputRow: { flexDirection: "row", padding: 12, borderTopWidth: 1, borderColor: "#222" },
  input: { flex: 1, backgroundColor: "#1a1a1a", color: "#fff", borderRadius: 8, padding: 10, borderWidth: 1, borderColor: "#333" },
  sendBtn: { backgroundColor: "#00ff88", borderRadius: 8, paddingHorizontal: 16, marginLeft: 8, justifyContent: "center" },
  sendText: { color: "#0a0a0a", fontWeight: "700" },
});
