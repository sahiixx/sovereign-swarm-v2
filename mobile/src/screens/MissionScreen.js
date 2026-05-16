import React, { useState } from "react";
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from "react-native";
import { api } from "../api/client";

export default function MissionScreen() {
  const [goal, setGoal] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!goal.trim()) return;
    setLoading(true);
    try {
      const res = await api.mission(goal.trim());
      setResult(res);
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <Text style={styles.header}>New Mission</Text>
      <TextInput
        style={styles.input}
        placeholder="Enter mission goal..."
        placeholderTextColor="#666"
        value={goal}
        onChangeText={setGoal}
        multiline
      />
      <TouchableOpacity style={styles.button} onPress={submit} disabled={loading}>
        <Text style={styles.buttonText}>{loading ? "Running..." : "Execute"}</Text>
      </TouchableOpacity>
      {loading && <ActivityIndicator color="#00ff88" style={{ marginTop: 20 }} />}
      {result && (
        <View style={styles.resultBox}>
          <Text style={styles.resultTitle}>Result</Text>
          <Text style={styles.resultText}>{JSON.stringify(result, null, 2)}</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { padding: 20, backgroundColor: "#0a0a0a", flexGrow: 1 },
  header: { fontSize: 24, fontWeight: "bold", color: "#00ff88", marginBottom: 16 },
  input: { backgroundColor: "#1a1a1a", color: "#fff", borderRadius: 8, padding: 12, minHeight: 80, textAlignVertical: "top", borderWidth: 1, borderColor: "#333" },
  button: { backgroundColor: "#00ff88", paddingVertical: 14, borderRadius: 8, marginTop: 16, alignItems: "center" },
  buttonText: { color: "#0a0a0a", fontSize: 16, fontWeight: "700" },
  resultBox: { backgroundColor: "#1a1a1a", borderRadius: 8, padding: 12, marginTop: 20, borderWidth: 1, borderColor: "#333" },
  resultTitle: { color: "#00ff88", fontSize: 16, fontWeight: "600", marginBottom: 8 },
  resultText: { color: "#ccc", fontSize: 12, fontFamily: "monospace" },
});
