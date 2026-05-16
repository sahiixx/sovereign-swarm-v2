import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";

export default function HomeScreen({ navigation }) {
  return (
    <View style={styles.container}>
      <Text style={styles.title}>SAHIIXX OS</Text>
      <Text style={styles.subtitle}>Sovereign Swarm v2.0</Text>
      <TouchableOpacity style={styles.button} onPress={() => navigation.navigate("Mission")}>
        <Text style={styles.buttonText}>New Mission</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.button} onPress={() => navigation.navigate("Chat")}>
        <Text style={styles.buttonText}>Chat</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.button} onPress={() => navigation.navigate("Status")}>
        <Text style={styles.buttonText}>Status</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", alignItems: "center", backgroundColor: "#0a0a0a" },
  title: { fontSize: 36, fontWeight: "bold", color: "#00ff88", marginBottom: 8 },
  subtitle: { fontSize: 16, color: "#888", marginBottom: 40 },
  button: { backgroundColor: "#1a1a1a", paddingVertical: 14, paddingHorizontal: 32, borderRadius: 8, marginVertical: 8, width: 200, alignItems: "center", borderWidth: 1, borderColor: "#00ff88" },
  buttonText: { color: "#00ff88", fontSize: 16, fontWeight: "600" },
});
