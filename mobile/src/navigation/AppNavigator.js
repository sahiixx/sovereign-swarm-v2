import React from "react";
import { createStackNavigator } from "@react-navigation/stack";
import { NavigationContainer } from "@react-navigation/native";
import HomeScreen from "../screens/HomeScreen";
import MissionScreen from "../screens/MissionScreen";
import ChatScreen from "../screens/ChatScreen";
import StatusScreen from "../screens/StatusScreen";

const Stack = createStackNavigator();

export default function AppNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerStyle: { backgroundColor: "#0a0a0a" }, headerTintColor: "#00ff88" }}>
        <Stack.Screen name="Home" component={HomeScreen} options={{ title: "SAHIIXX OS" }} />
        <Stack.Screen name="Mission" component={MissionScreen} options={{ title: "Mission" }} />
        <Stack.Screen name="Chat" component={ChatScreen} options={{ title: "Chat" }} />
        <Stack.Screen name="Status" component={StatusScreen} options={{ title: "Status" }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
