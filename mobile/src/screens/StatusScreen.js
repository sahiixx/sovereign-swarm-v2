import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ActivityIndicator } from "react-native";
import { api } from "../api/client";

export default function StatusScreen() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus({ error: true }));
  }, []);

  return (
    <View style={styles.container}>
      <Text style={styles.header}>System Status</Text>
      {!status && <ActivityIndicator color="#00ff88" />}
      {status && (
        <View style={styles.card}>
          <Text style={styles.label}>DSL Ready: <Text style={styles.value}>{status.dsl_ready ? "Yes" : "No"}</Text></Text>
          <Text style={styles.label}>Service: <Text style={styles.value}>{status.service}</Text></Text>
          <Text style={styles.label}>Timestamp: <Text style={styles.value}>{status.timestamp}</Text></Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0a0a0a", padding: 20 },
  header: { fontSize: 24, fontWeight: "bold", color: "#00ff88", marginBottom: 16 },
  card: { backgroundColor: "#1a1a1a", borderRadius: 8, padding: 16, borderWidth: 1, borderColor: "#333" },
  label: { color: "#888", fontSize: 14, marginVertical: 4 },
  value: { color: "#fff", fontWeight: "600" },
});
