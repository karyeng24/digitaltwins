from openai import OpenAI
import json
import gradio as gr
from gradio.themes import Soft
import networkx as nx
import matplotlib.pyplot as plt
from io import BytesIO
import re
import numpy as np
import matplotlib.patches as patches
import random
import time
import os


# Initialize the client with OpenRouter API
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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"  # Replace with your actual API key
)

# Color scheme for different node types
NODE_COLORS = {
    "router": "#f0ad4e",
    "switch": "#5bc0de",
    "server": "#5cb85c",
    "computer": "#6c757d",
    "firewall": "#d9534f",
    "cloud": "#b8daff",
    "hub": "#8ff0a4",
    "ethernet_switch": "#26a269",
    "load_balancer": "#e83e8c",
    "database": "#6f42c1",
    "wireless_ap": "#fd7e14",
    "voip_phone": "#20c997",
    "printer": "#343a40",
    "storage": "#17a2b8",
    "generic": "#888888"
}

class NetworkDiagramManager:
    def __init__(self):
        self.G = nx.Graph()
        self.node_positions = {}
        self.node_types = {}
        self.node_info = {}  # Add this line to store network info
        self.subnet_counter = 0 
        self.node_names = {}
        self.node_details = {}  # Add node details for more information
        self.edge_types = {}  # Store edge types for different connection styles
        self.connections = []
        self.diagram_state = {
            "nodes": [],
            "connections": []
        }

    def _generate_ip_address(self, node_type):
        """Auto-generates IP address based on node type"""
        self.subnet_counter += 1
        base_subnet = self.subnet_counter % 3
        
        if base_subnet == 0:
            network = f"10.{self.subnet_counter % 256}.0.0/24"
            host = 1 + (self.subnet_counter // 256) % 254
            ip = f"10.{self.subnet_counter % 256}.0.{host}"
        elif base_subnet == 1:
            network = f"172.16.{self.subnet_counter % 16}.0/24"
            host = 1 + (self.subnet_counter // 16) % 254
            ip = f"172.16.{self.subnet_counter % 16}.{host}"
        else:
            network = f"192.168.{self.subnet_counter % 256}.0/24"
            host = 1 + (self.subnet_counter // 256) % 254
            ip = f"192.168.{self.subnet_counter % 256}.{host}"
        
        return {
            "ip": ip,
            "network": network,
            "subnet_mask": "255.255.255.0",
            "type": node_type
        }

    def get_node_info(self, node_id):
        """Returns network information for a node"""
        if node_id not in self.node_info:
            node_type = self.node_types.get(node_id, "generic")
            self.node_info[node_id] = self._generate_ip_address(node_type)
            self.node_info[node_id].update({
                "name": self.node_names.get(node_id, node_id),
                "connections": [tgt for src, tgt in self.connections if src == node_id]
            })
        return self.node_info[node_id]    

    def add_node(self, node_id, name, node_type="generic", details=None):
        """
        Add a node to the network diagram
        
        Args:
            node_id (str): Unique identifier for the node
            name (str): Human-readable name for the node
            node_type (str): Type of node (router, switch, server, etc.)
            details (dict): Additional node properties
        """
        if details is None:
            details = {}
        
        # Add to graph
        self.G.add_node(node_id)
        
        # Store node properties
        self.node_types[node_id] = node_type.lower()
        self.node_names[node_id] = name
        self.node_details[node_id] = details
        
        # Update diagram state
        self._update_diagram_state()

    def add_connection(self, source, target, connection_type="standard"):
        """
        Add a connection between two nodes
        
        Args:
            source (str): Source node ID
            target (str): Target node ID
            connection_type (str): Type of connection (standard/dashed/thick/etc.)
        
        Returns:
            bool: True if connection was added, False otherwise
        """
        # Check if nodes exist
        if source not in self.G.nodes() or target not in self.G.nodes():
            print(f"[WARNING] Cannot add connection between non-existent nodes: {source} and {target}")
            return False
        
        # Add to graph and internal tracking
        self.G.add_edge(source, target)
        connection = (source, target)
        
        # Only add to connections list if not already present
        if connection not in self.connections and (target, source) not in self.connections:
            self.connections.append(connection)
        
        # Store connection type
        self.edge_types[connection] = connection_type
        
        # Update diagram state
        self._update_diagram_state()
        return True    
    
    def reset_diagram(self):
        self.G = nx.Graph()
        self.node_positions = {}
        self.node_types = {}
        self.node_names = {}
        self.node_details = {}
        self.edge_types = {}
        self.connections = []
        self.diagram_state = {
            "nodes": [],
            "connections": []
        }
    
    def update_from_ai_response(self, ai_response):
        try:
            # Try to extract JSON from a ```json block if present
            json_match = re.search(r'```json\n(.*?)\n```', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = ai_response.strip()

            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON decoding failed: {e}")
                return False

            # Validate structure
            if not isinstance(data, dict):
                print("[ERROR] AI response JSON is not a dictionary")
                return False

            nodes = data.get("nodes", [])
            connections = data.get("connections", [])

            if not isinstance(nodes, list) or not isinstance(connections, list):
                print("[ERROR] 'nodes' or 'connections' field is not a list")
                return False

            # Add nodes safely
            for node in nodes:
                try:
                    node_id = node["id"]
                    name = node.get("name", node_id)
                    ntype = node.get("type", "generic")
                    details = node.get("details", {})
                    self.add_node(node_id, name, ntype, details)
                except Exception as e:
                    print(f"[WARNING] Failed to add node {node}: {e}")

            # Add connections safely
            for conn in connections:
                try:
                    source = conn["source"]
                    target = conn["target"]
                    conn_type = conn.get("type", "standard")
                    self.add_connection(source, target, conn_type)
                except Exception as e:
                    print(f"[WARNING] Failed to add connection {conn}: {e}")

            return True

        except Exception as e:
            print(f"[ERROR] Unexpected error in update_from_ai_response: {e}")
            return False
    
    def _merge_state(self, new_state):
        """Merge new diagram state with existing state"""
        # Track existing node IDs to avoid duplicates
        existing_node_ids = set(self.node_names.keys())
        
        # Add new nodes
        for node in new_state.get("nodes", []):
            node_id = node.get("id")
            
            # Skip if this node already exists
            if node_id in existing_node_ids:
                continue
                
            node_name = node.get("name", node_id)
            node_type = node.get("type", "generic").lower()
            details = node.get("details", {})
            
            self.G.add_node(node_id)
            self.node_types[node_id] = node_type
            self.node_names[node_id] = node_name
            self.node_details[node_id] = details
            
            # Add to existing node IDs set
            existing_node_ids.add(node_id)
        
        # Add new connections
        existing_connections = set(self.connections)
        for conn in new_state.get("connections", []):
            source = conn.get("source")
            target = conn.get("target")
            conn_type = conn.get("type", "standard")
            
            # Only add connection if both nodes exist
            if source in existing_node_ids and target in existing_node_ids:
                connection = (source, target)
                reverse_connection = (target, source)
                
                # Skip if this connection already exists
                if connection in existing_connections or reverse_connection in existing_connections:
                    continue
                
                self.G.add_edge(source, target)
                self.connections.append(connection)
                self.edge_types[connection] = conn_type
                existing_connections.add(connection)
        
        # Update the diagram state to reflect the current state
        self._update_diagram_state()
    
    def _update_diagram_state(self):
        """Update diagram state from internal representation"""
        nodes = []
        for node_id in self.G.nodes():
            nodes.append({
                "id": node_id,
                "name": self.node_names.get(node_id, node_id),
                "type": self.node_types.get(node_id, "generic"),
                "details": self.node_details.get(node_id, {})
            })
        
        connections = []
        for source, target in self.connections:
            connections.append({
                "source": source,
                "target": target,
                "type": self.edge_types.get((source, target), "standard")
            })
        
        self.diagram_state = {
            "nodes": nodes,
            "connections": connections
        }
    
    def _draw_server_icon(self, ax, pos, radius=0.03, color="#66BB6A"):
        """Compact modern server icon"""
        x, y = pos
        width, height = radius * 1.8, radius * 2.2
        
        # Main chassis
        chassis = patches.Rectangle(
            (x - width/2, y - height/2), width, height,
            linewidth=1, edgecolor="#333", facecolor=color, zorder=5
        )
        ax.add_patch(chassis)
        
        # Rack rails
        for i in np.linspace(-0.7, 0.7, 3):
            ax.plot(
                [x - width/2.5, x + width/2.5],
                [y + i*height/3, y + i*height/3],
                color="#333", linewidth=0.8, zorder=6
            )
        
        # Status LED
        led = patches.Circle(
            (x + width/3, y - height/3),
            radius * 0.06,
            facecolor="#00FF40", edgecolor="#333", zorder=7
        )
        ax.add_patch(led)
        
        return chassis

    def _draw_router_icon(self, ax, pos, radius=0.03, color="#FFA726"):
        """Compact modern router icon"""
        x, y = pos
        size = radius * 1.6
        
        # Main body
        body = patches.Rectangle(
            (x - size/2, y - size/2), size, size,
            linewidth=1, edgecolor="#333", facecolor=color, zorder=5
        )
        ax.add_patch(body)
        
        # Antennas
        for i in [-1, 1]:
            ax.plot(
                [x + i*size/3, x + i*size/1.8],
                [y + size/4, y + size/2.2],
                color="#333", linewidth=1, solid_capstyle="round", zorder=4
            )
        
        # Ports
        for i in np.linspace(-0.6, 0.6, 5):
            port = patches.Rectangle(
                (x + i*size/2, y - size/2.2),
                width=radius*0.2, height=radius*0.12,
                facecolor="#333", zorder=6
            )
            ax.add_patch(port)
        
        return body
    
    def _draw_firewall_icon(self, ax, pos, radius=0.05, color="#d9534f"):
        """Draw a simple firewall icon with shield shape"""
        x, y = pos
        
        # Create shield shape (simplified)
        shield_points = [
            (x, y + radius * 1.2),          # Top point
            (x - radius * 0.9, y - radius),  # Bottom left
            (x + radius * 0.9, y - radius)   # Bottom right
        ]
        
        shield = patches.Polygon(
            shield_points,
            closed=True,
            linewidth=1.5,
            edgecolor="black",
            facecolor=color,
            zorder=5
        )
        ax.add_patch(shield)
        
        # Add simple crossed lines inside (representing protection)
        line1 = plt.Line2D(
            [x - radius * 0.5, x + radius * 0.5],
            [y - radius * 0.3, y + radius * 0.3],
            color="white", linewidth=1.5, zorder=6
        )
        line2 = plt.Line2D(
            [x - radius * 0.5, x + radius * 0.5],
            [y + radius * 0.3, y - radius * 0.3],
            color="white", linewidth=1.5, zorder=6
        )
        ax.add_line(line1)
        ax.add_line(line2)
        
        return shield
    
    def _draw_switch_icon(self, ax, pos, radius=0.03, color="#4FC3F7"):
        """Compact modern switch icon"""
        x, y = pos
        width, height = radius * 2.5, radius * 1.5
        
        # Main body
        body = patches.Rectangle(
            (x - width/2, y - height/2), width, height,
            linewidth=1, edgecolor="#333", facecolor=color, zorder=5
        )
        ax.add_patch(body)
        
        # Ports (simplified)
        for i in np.linspace(-0.8, 0.8, 6):
            port = patches.Rectangle(
                (x + i*width/2.5, y - height/3),
                width=radius*0.18, height=radius*0.3,
                facecolor="#333", zorder=6
            )
            ax.add_patch(port)
        
        return body

    
    def _draw_pc_icon(self, ax, pos, radius=0.05, color="#78909C"):
        """Modern PC icon with monitor and stand"""
        x, y = pos
        
        # Monitor body
        monitor = patches.Rectangle(
            (x - radius*1.0, y - radius*0.8),  # Adjusted position
            width=radius*2.0, 
            height=radius*1.6,
            linewidth=1.5, 
            edgecolor="#333", 
            facecolor=color, 
            zorder=5
        )
        ax.add_patch(monitor)
        
        # Screen area
        screen = patches.Rectangle(
            (x - radius*0.9, y - radius*0.7),
            width=radius*1.8, 
            height=radius*1.2,
            facecolor="#263238", 
            edgecolor="none", 
            zorder=6
        )
        ax.add_patch(screen)
        
        # Monitor stand base (wider rectangle at bottom)
        stand_base = patches.Rectangle(
            (x - radius*0.5, y - radius*1.1),
            width=radius*1.0, 
            height=radius*0.2,
            linewidth=1,
            edgecolor="#333",
            facecolor=color,
            zorder=4
        )
        ax.add_patch(stand_base)
        
        # Monitor neck (connecting piece)
        stand_neck = patches.Rectangle(
            (x - radius*0.2, y - radius*0.9),
            width=radius*0.4, 
            height=radius*0.2,
            linewidth=1,
            edgecolor="#333",
            facecolor=color,
            zorder=4
        )
        ax.add_patch(stand_neck)
        
        # Optional: Add a power indicator light
        power_light = patches.Circle(
            (x + radius*0.7, y - radius*0.7),
            radius=radius*0.08,
            facecolor="#00FF00",  # Green power light
            edgecolor="none",
            zorder=7
        )
        ax.add_patch(power_light)
        
        return monitor

    
    def _draw_cloud_icon(self, ax, pos, radius=0.05, color="#90CAF9"):
        """Modern cloud icon with multiple overlapping ellipses"""
        x, y = pos
        
        # Main cloud body (larger ellipse)
        main_cloud = patches.Ellipse(
            (x, y), 
            width=radius*3.5, 
            height=radius*2.2,
            linewidth=1.5, 
            edgecolor="#0077CC", 
            facecolor=color,
            zorder=5
        )
        ax.add_patch(main_cloud)
        
        # Cloud puff 1 (top left)
        puff1 = patches.Ellipse(
            (x - radius*0.8, y + radius*0.5), 
            width=radius*1.8, 
            height=radius*1.5,
            linewidth=1, 
            edgecolor="#0077CC", 
            facecolor=color,
            zorder=6
        )
        ax.add_patch(puff1)
        
        # Cloud puff 2 (top right)
        puff2 = patches.Ellipse(
            (x + radius*0.9, y + radius*0.4), 
            width=radius*1.6, 
            height=radius*1.3,
            linewidth=1, 
            edgecolor="#0077CC", 
            facecolor=color,
            zorder=6
        )
        ax.add_patch(puff2)
        
        # Cloud puff 3 (bottom left)
        puff3 = patches.Ellipse(
            (x - radius*1.1, y - radius*0.2), 
            width=radius*1.4, 
            height=radius*1.2,
            linewidth=1, 
            edgecolor="#0077CC", 
            facecolor=color,
            zorder=6
        )
        ax.add_patch(puff3)
        
        # Optional: Add some subtle inner highlights
        highlight = patches.Ellipse(
            (x - radius*0.3, y + radius*0.2), 
            width=radius*0.8, 
            height=radius*0.5,
            linewidth=0, 
            facecolor="white",
            alpha=0.3,
            zorder=7
        )
        ax.add_patch(highlight)
        
        return main_cloud

    def _draw_hub_icon(self, ax, pos, radius=0.05, color="#8ff0a4"):
        """Draw a simplified hub icon (like GNS3 style)"""
        x, y = pos

        # Outer circle (hub)
        outer_circle = plt.Circle((x, y), radius, facecolor=color, edgecolor="black", linewidth=1.5, zorder=5)
        ax.add_patch(outer_circle)

        # Optional: Inner dot for a more 'hub' feel
        inner_circle = plt.Circle((x, y), radius*0.3, facecolor="black", zorder=6)
        ax.add_patch(inner_circle)

        return outer_circle

    
    def _draw_ethernet_switch_icon(self, ax, pos, radius=0.05, color="#26a269"):
        """Draw a simplified ethernet switch icon (like GNS3 style)"""
        x, y = pos
        width, height = radius * 3, radius * 2  # Slightly more square

        # Main rectangle (switch body)
        rect = patches.FancyBboxPatch(
            (x - width/2, y - height/2),
            width, height,
            boxstyle="round,pad=0.02",  # Rounded corners
            linewidth=1.5,
            edgecolor="black",
            facecolor=color,
            zorder=5
        )
        ax.add_patch(rect)

        # Add 2–3 small "ports" (circles) at the top
        port_radius = radius * 0.2
        num_ports = 3
        spacing = width / (num_ports + 1)
        for i in range(num_ports):
            port_x = x - width/2 + spacing * (i + 1)
            port_y = y + height/4
            port = plt.Circle((port_x, port_y), port_radius, facecolor="white", edgecolor="black", linewidth=0.5, zorder=6)
            ax.add_patch(port)

        return rect

    
    def _draw_load_balancer_icon(self, ax, pos, radius=0.03, color="#E83E8C"):
        """Compact load balancer icon"""
        x, y = pos
        
        # Body
        body = patches.Rectangle(
            (x - radius*0.8, y - radius*0.6),
            width=radius*1.6, height=radius*1.2,
            linewidth=1, edgecolor="#333", facecolor=color, zorder=5
        )
        ax.add_patch(body)
        
        # Arrows
        for i in [-0.5, 0, 0.5]:
            ax.arrow(
                x + i*radius*0.6, y + radius*0.2,
                0, -radius*0.8,
                head_width=radius*0.15, head_length=radius*0.15,
                fc="#333", ec="none", zorder=6
            )
        
        return body
    
    def _draw_database_icon(self, ax, pos, radius=0.03, color="#6F42C1"):
        """Compact database icon"""
        x, y = pos
        
        # Body
        body = patches.Ellipse(
            (x, y), width=radius*1.8, height=radius*1.2,
            linewidth=1, edgecolor="#333", facecolor=color, zorder=5
        )
        ax.add_patch(body)
        
        # Top
        top = patches.Ellipse(
            (x, y + radius*0.3), width=radius*1.8, height=radius*0.4,
            linewidth=1, edgecolor="#333", facecolor=color, zorder=6
        )
        ax.add_patch(top)
        
        return body

    
    def _draw_wireless_icon(self, ax, pos, radius=0.03, color="#FD7E14"):
        """Compact wireless AP icon"""
        x, y = pos
        
        # Base
        base = patches.Circle(
            (x, y), radius*0.6,
            linewidth=1, edgecolor="#333", facecolor=color, zorder=5
        )
        ax.add_patch(base)
        
        # Waves
        for i, r in enumerate([1.0, 0.7, 0.4], 1):
            wave = patches.Arc(
                (x, y), width=r*radius*2, height=r*radius*2,
                theta1=210, theta2=330, linewidth=1,
                linestyle=(0, (i, i)), color="#333", zorder=4
            )
            ax.add_patch(wave)
        
        return base

    
    def _draw_voip_phone_icon(self, ax, pos, radius=0.05, color="#20c997"):
        """Draw a simplified VoIP phone icon (like GNS3 style)"""
        x, y = pos
        width, height = radius * 2.2, radius * 3  # Slightly slimmer

        # Main body (rounded rectangle)
        rect = patches.FancyBboxPatch(
            (x - width/2, y - height/2),
            width, height,
            boxstyle="round,pad=0.02",
            linewidth=1.5,
            edgecolor="black",
            facecolor=color,
            zorder=5
        )
        ax.add_patch(rect)

        # Simple screen (small rounded box near top)
        screen_height = height * 0.25
        screen = patches.FancyBboxPatch(
            (x - width * 0.35, y + height * 0.15),
            width * 0.7, screen_height,
            boxstyle="round,pad=0.02",
            linewidth=1,
            edgecolor="black",
            facecolor="white",
            zorder=6
        )
        ax.add_patch(screen)

        # Single "button" circle at bottom center (suggests keypad)
        button = plt.Circle((x, y - height * 0.25), width * 0.15, facecolor="white", edgecolor="black", linewidth=0.8, zorder=6)
        ax.add_patch(button)

        return rect

    
    def _draw_storage_icon(self, ax, pos, radius=0.05, color="#17a2b8"):
        """Draw a storage device icon"""
        x, y = pos
        width, height = radius*3, radius*2.2
        
        # Draw storage box
        rect = patches.Rectangle((x-width/2, y-height/2), width, height, linewidth=1, 
                              edgecolor="black", facecolor=color, zorder=5)
        ax.add_patch(rect)
        
        # Draw disks
        for i in range(3):
            for j in range(2):
                disk_x = x - width/4 + j * width/2
                disk_y = y - height/3 + i * height/3
                disk = patches.Rectangle((disk_x-width*0.1, disk_y-height*0.08), width*0.2, height*0.16, 
                                    linewidth=1, edgecolor="black", facecolor="white", zorder=6)
                ax.add_patch(disk)
        
        return rect
        
    def _draw_node_icon(self, ax, node_id, pos):
        """Draw the appropriate icon for a node based on type"""
        node_type = self.node_types.get(node_id, "generic")
        color = self.get_node_color(node_id)
        x, y = pos
        
        # Choose the appropriate icon drawing function
        if node_type == "server" or node_type == "web_server":
            icon = self._draw_server_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "router":
            icon = self._draw_router_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "switch":
            icon = self._draw_switch_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "firewall":
            icon = self._draw_firewall_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "computer" or node_type == "client":
            icon = self._draw_pc_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "cloud":
            icon = self._draw_cloud_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "hub":
            icon = self._draw_hub_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "ethernet_switch":
            icon = self._draw_ethernet_switch_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "load_balancer":
            icon = self._draw_load_balancer_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "database" or node_type == "db":
            icon = self._draw_database_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "wireless_ap" or node_type == "wifi":
            icon = self._draw_wireless_ap_icon(ax, pos, radius=0.05, color=color)
        elif node_type == "voip_phone" or node_type == "phone":
            icon = self._draw_voip_phone_icon(ax, pos, radius=0.05, color=color)
        else:
            icon = self._draw_storage_icon(ax, pos, radius=0.05, color=color)
        
        icon.node_id = node_id
        return icon
    
    def get_node_color(self, node_id):
        """Get the color for a node based on its type"""
        node_type = self.node_types.get(node_id, "generic")
        
        # Map to supported color types or fall back to generic
        if node_type not in NODE_COLORS:
            if node_type == "client":
                node_type = "computer"
            elif node_type == "web_server":
                node_type = "server"
            elif node_type == "db" or node_type == "database_server":
                node_type = "database"
            elif node_type == "wifi":
                node_type = "wireless_ap"
            elif node_type == "phone":
                node_type = "voip_phone"
            elif node_type == "nas":
                node_type = "storage"
            else:
                node_type = "generic"
                
        return NODE_COLORS.get(node_type, "#888888")
    
    def _optimize_positions(self, pos, iterations=50):
        """Optimize node positions to reduce edge crossings and improve layout"""
        # Create a copy of positions to work with
        new_pos = pos.copy()
        
        # Apply force-directed adjustments
        for _ in range(iterations):
            # Calculate repulsive forces between nodes
            for node1 in self.G.nodes():
                force_x, force_y = 0, 0
                
                # Repulsion from other nodes
                for node2 in self.G.nodes():
                    if node1 != node2:
                        x1, y1 = new_pos[node1]
                        x2, y2 = new_pos[node2]
                        
                        dx = x1 - x2
                        dy = y1 - y2
                        
                        # Avoid division by zero
                        distance = max(0.01, (dx**2 + dy**2)**0.5)
                        
                        # Normalized force inversely proportional to distance
                        force = 0.001 / (distance**2)
                        
                        # Add to total force
                        force_x += dx * force
                        force_y += dy * force
                
                # Attractive forces from connected nodes
                for neighbor in self.G.neighbors(node1):
                    x1, y1 = new_pos[node1]
                    x2, y2 = new_pos[neighbor]
                    
                    dx = x2 - x1
                    dy = y2 - y1
                    
                    # Calculate distance
                    distance = max(0.01, (dx**2 + dy**2)**0.5)
                    
                    # Force proportional to distance
                    force = 0.002 * distance
                    
                    # Add to total force
                    force_x += dx * force
                    force_y += dy * force
                
                # Update position with constraints
                new_pos[node1] = (
                    max(0.05, min(0.95, new_pos[node1][0] + force_x * 0.1)),
                    max(0.1, min(0.9, new_pos[node1][1] + force_y * 0.1))
                )
        
        return new_pos
    
    def render_diagram(self, export=False, optimize=True, highlight_node=None):
        if not self.G.nodes:
            # Return empty diagram
            plt.figure(figsize=(10, 8))
            plt.text(0.5, 0.5, "Empty diagram. Add components using commands.", 
                    ha='center', va='center')
            plt.axis('off')
            if export:
                buf = BytesIO()
                plt.savefig(buf, format='png', dpi=150)
                plt.close()
                buf.seek(0)
                return buf
            return plt.gcf()
        
        # Create initial positions for nodes
        pos = {}
        node_count = len(self.G.nodes())
        
        if node_count > 0:
            for i, node in enumerate(self.G.nodes()):
                # Add slight randomness to initial position for better optimization
                x_pos = (i + 1) / (node_count + 1) + random.uniform(-0.05, 0.05)
                x_pos = max(0.1, min(0.9, x_pos))  # Keep within bounds
                y_pos = 0.5 + random.uniform(-0.2, 0.2)
                y_pos = max(0.1, min(0.9, y_pos))
                pos[node] = (x_pos, y_pos)
        
        # Optimize positions if requested
        if optimize and len(self.G.nodes()) > 1:
            pos = self._optimize_positions(pos)
        
        self.node_positions = pos
        
        # Create the figure with a white background
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='white')
        ax.set_facecolor('white')
        
        # Draw edges with different styles based on edge_type
        for u, v in self.G.edges():
            # Get edge type
            edge_type = "standard"
            if (u, v) in self.edge_types:
                edge_type = self.edge_types[(u, v)]
            elif (v, u) in self.edge_types:
                edge_type = self.edge_types[(v, u)]
            
            # Draw based on edge type
            x1, y1 = pos[u]
            x2, y2 = pos[v]
            
            # Define parameters based on edge type
            if edge_type == "dashed":
                linestyle = "dashed"
                color = "#6c757d"
                width = 1.5
                rad = 0.15
            elif edge_type == "thick":
                linestyle = "solid"
                color = "#0d6efd"
                width = 3
                rad = 0.1
            elif edge_type == "red":
                linestyle = "solid"
                color = "#dc3545"
                width = 2
                rad = 0.15
            elif edge_type == "green":
                linestyle = "solid"
                color = "#198754"
                width = 2
                rad = 0.15
            elif edge_type == "wireless":
                linestyle = (0, (3, 2, 1, 2))  # Dot-dash pattern
                color = "#fd7e14"
                width = 2
                rad = 0.15
            else:  # standard
                linestyle = "solid"
                color = "#6c757d"
                width = 2
                rad = 0.15
                
            # Create a slight curve for each edge
            if abs(y1 - y2) > 0.1:  # Vertical connections get more curve
                rad = 0.25
                
            # Draw connection with specified style
            nx.draw_networkx_edges(
                self.G, pos,
                edgelist=[(u, v)],
                ax=ax,
                width=width,
                alpha=0.7,
                edge_color=color,
                style=linestyle,
                connectionstyle=f'arc3,rad={rad}',
                arrows=True,
                arrowstyle='->'
            )
        
        # Highlight the selected node if specified
        if highlight_node and highlight_node in pos:
            x, y = pos[highlight_node]
            highlight_circle = plt.Circle(
                (x, y), 
                0.08,  # Slightly larger radius for highlight
                color='yellow', 
                alpha=0.3,
                zorder=3
            )
            ax.add_patch(highlight_circle)
        
        # Draw nodes with custom icons
        for node in self.G.nodes():
            # Draw the appropriate icon for this node type
            icon = self._draw_node_icon(ax, node, pos[node])
            icon.node_id = node  # Store node ID for click handling
            
            # Add node name with a nice background
            text = ax.text(
                pos[node][0], pos[node][1]-0.07, 
                self.node_names.get(node, node),
                ha='center',
                va='top',
                fontsize=10,
                weight='bold',
                bbox=dict(
                    facecolor='white', 
                    alpha=0.8, 
                    boxstyle="round,pad=0.3",
                    edgecolor='gray'
                ),
                zorder=10
            )
            
            # Add details tooltip if any
            details = self.node_details.get(node, {})
            if details:
                detail_text = []
                for k, v in details.items():
                    detail_text.append(f"{k}: {v}")
                
                if detail_text:
                    details_str = "\n".join(detail_text)
                    ax.annotate(
                        details_str,
                        xy=pos[node],
                        xytext=(pos[node][0], pos[node][1]+0.05),
                        bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", ec="b", lw=1, alpha=0.8),
                        ha="center", va="bottom",
                        size=8,
                        xycoords='data',
                        textcoords='data',
                        arrowprops=dict(arrowstyle="-", connectionstyle="arc3,rad=0", alpha=0.6)
                    )
        
        # Add title
        ax.set_title("Network Diagram", fontsize=16, weight='bold', pad=20)
        
        # Add timestamp
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        ax.text(
            0.98, 0.02, 
            f"Generated: {timestamp}", 
            ha='right', 
            va='bottom', 
            fontsize=8, 
            color='gray',
            transform=ax.transAxes
        )
        
        # Set axis limits with some padding
        ax.set_xlim(-0.1, 1.1)
        ax.set_ylim(0.1, 1.1)
        ax.axis('off')
        plt.tight_layout()
        
        # Store the current figure and axes for click handling
        self.current_fig = fig
        self.current_ax = ax
        
        if export:
            buf = BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', dpi=150, facecolor='white')
            plt.close()
            buf.seek(0)
            return buf
        else:
            return fig
    
    def export_svg(self):
        """Export diagram as SVG without using CairoSVG"""
        if not self.G.nodes:
            return None
            
        # Create figure for SVG export
        fig = self.render_diagram(export=False)
        
        # Export to SVG in memory
        buf = BytesIO()
        fig.savefig(buf, format='svg', bbox_inches='tight', dpi=150, facecolor='white')
        plt.close(fig)
        buf.seek(0)
        
        # Return SVG content as string
        svg_content = buf.getvalue().decode('utf-8')
        return svg_content
    
    def export_json(self):
        """Export diagram as JSON for later import"""
        json_data = {
            "nodes": [],
            "connections": []
        }
        
        # Add nodes with all details
        for node_id in self.G.nodes():
            json_data["nodes"].append({
                "id": node_id,
                "name": self.node_names.get(node_id, node_id),
                "type": self.node_types.get(node_id, "generic"),
                "details": self.node_details.get(node_id, {})
            })
        
        # Add connections
        for source, target in self.connections:
            json_data["connections"].append({
                "source": source,
                "target": target,
                "type": self.edge_types.get((source, target), "standard")
            })
        
        return json.dumps(json_data, indent=2)
    
    def import_json(self, json_str):
        """Import diagram from JSON"""
        try:
            # Reset current diagram
            self.reset_diagram()
            
            # Load new diagram
            data = json.loads(json_str)
            
            # Use merge state to load diagram
            self._merge_state(data)
            
            return True
        except Exception as e:
            print(f"Error importing diagram: {e}")
            return False
        
    def remove_node(self, node_id):
        """Remove a node and all its connections from the diagram"""
        if node_id in self.G.nodes():
            # Remove from graph
            self.G.remove_node(node_id)
            
            # Remove from dictionaries
            if node_id in self.node_types:
                del self.node_types[node_id]
            if node_id in self.node_names:
                del self.node_names[node_id]
            if node_id in self.node_details:
                del self.node_details[node_id]
            if node_id in self.node_positions:
                del self.node_positions[node_id]
                
            # Remove connections involving this node
            self.connections = [(src, tgt) for src, tgt in self.connections 
                            if src != node_id and tgt != node_id]
            
            # Remove edge types involving this node
            edge_types_to_remove = []
            for (src, tgt) in self.edge_types.keys():
                if src == node_id or tgt == node_id:
                    edge_types_to_remove.append((src, tgt))
            
            for edge in edge_types_to_remove:
                del self.edge_types[edge]
                
            # Update diagram state
            self._update_diagram_state()
            return True
        return False

    def remove_connection(self, source, target):
        """Remove a connection between two nodes"""
        # Check both directions
        if (source, target) in self.connections:
            self.connections.remove((source, target))
            if (source, target) in self.edge_types:
                del self.edge_types[(source, target)]
            self.G.remove_edge(source, target)
            self._update_diagram_state()
            return True
        elif (target, source) in self.connections:
            self.connections.remove((target, source))
            if (target, source) in self.edge_types:
                del self.edge_types[(target, source)]
            self.G.remove_edge(target, source)
            self._update_diagram_state()
            return True
        else:
            # If connection not found in internal list but exists in graph, try removing directly from graph
            if self.G.has_edge(source, target):
                self.G.remove_edge(source, target)
                self._update_diagram_state()
                return True
            elif self.G.has_edge(target, source):
                self.G.remove_edge(target, source)
                self._update_diagram_state()
                return True
        return False

def process_command(command, diagram_manager, history):
    # Reset diagram only on explicit create command and if diagram is empty
    if ("create" in command.lower() or "new" in command.lower()) and "diagram" in command.lower() and not diagram_manager.G.nodes:
        diagram_manager.reset_diagram()

    # Check for invalid commands that just say "add xyz to network"
    if re.match(r'^\s*add\s+\w+\s+(?:to\s+network|to\s+\w+)?\s*$', command, re.IGNORECASE):
        return "Error: Please specify what to add and how to connect it. Example: 'Add a server named xyz and connect it to router1'", None

    # Build current diagram state description
    current_state_description = "The current diagram is empty. " if not diagram_manager.G.nodes else "The current diagram contains the following elements: "
    if diagram_manager.G.nodes:
        nodes_str = ", ".join([f"{node_id} ({diagram_manager.node_types.get(node_id, 'generic')})"
                              for node_id in diagram_manager.G.nodes()])
        current_state_description += f"Nodes: {nodes_str}. "

        if diagram_manager.connections:
            connection_str = ", ".join([f"{src} → {tgt}" for src, tgt in diagram_manager.connections])
            current_state_description += f"Connections: {connection_str}."

    # Detect if command is a removal
    remove_keywords = ["remove", "delete", "eliminate", "get rid of"]
    is_remove_command = any(keyword in command.lower() for keyword in remove_keywords)

    # Build system prompt with strict JSON format requirements
    system_message = f"""You are a network diagram assistant. Generate JSON representations of network diagrams based on user commands.

{current_state_description}

Respond STRICTLY with a JSON object with EXACTLY these field names:
{{
    "nodes": [
        {{"id": "unique_id", "name": "Human Readable Name", "type": "router|switch|server|computer|firewall|cloud|hub|ethernet_switch|load_balancer|database|wireless_ap|voip_phone|printer|storage", "details": {{}}}}
    ],
    "connections": [
        {{"source": "node1_id", "target": "node2_id", "type": "standard|dashed|thick|red|green|wireless"}}
    ]
}}

IMPORTANT: 
- Use ONLY "nodes" and "connections" as top-level keys
- Never use variations like "node" or "connection"
- Include ALL required fields for each node and connection
- If the command is unclear or incomplete, respond with {{"error": "Please provide more details about what you want to add or connect"}}
- Verify that referenced nodes exist before creating connections"""

    if is_remove_command:
        system_message += """
For removal commands, respond STRICTLY with:
{
    "remove": {
        "nodes": ["node_id1", "node_id2"],
        "connections": [{"source": "node1_id", "target": "node2_id"}]
    }
}"""

    # Ensure history is not None
    if history is None:
        history = []

    # Build chat messages
    messages = [{"role": "system", "content": system_message}]
    recent_history = history[-5:] if len(history) > 5 else history
    for entry in recent_history:
        messages.append({"role": "user", "content": entry[0]})
        if len(entry) > 1 and entry[1]:
            messages.append({"role": "assistant", "content": entry[1]})
    messages.append({"role": "user", "content": command})

    try:
        # Call API
        completion = client.chat.completions.create(
            model="deepseek/deepseek-r1:free",
            messages=messages,
            response_format={"type": "json_object"}  # Force JSON response
        )

        if not completion or not hasattr(completion, 'choices') or len(completion.choices) == 0:
            return "Error: API returned an invalid response. Please try again.", None

        response = completion.choices[0].message.content
        if not response:
            return "Error: API returned an empty response. Please try again.", None

        print("Raw AI response:", response)  # Debug output

        # Try to extract JSON from response
        json_match = re.search(r'```json\n(.*?)\n```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = response.strip()

        try:
            data = json.loads(json_str)
            
            # Check for error response from AI
            if "error" in data:
                return f"Error: {data['error']}", None
                
            # Normalize key names to handle variations
            if "node" in data and "nodes" not in data:
                data["nodes"] = data.pop("node")
            if "connection" in data and "connections" not in data:
                data["connections"] = data.pop("connection")

            # Handle removal commands
            if is_remove_command and "remove" in data:
                removed_nodes = data["remove"].get("nodes", [])
                removed_connections = data["remove"].get("connections", [])
                
                # Check if nodes to remove exist
                missing_nodes = [node_id for node_id in removed_nodes if node_id not in diagram_manager.G.nodes()]
                if missing_nodes:
                    return f"Error: Cannot remove non-existent nodes: {', '.join(missing_nodes)}", None
                
                # Check if connections to remove exist
                existing_connections = set(diagram_manager.connections)
                missing_connections = []
                for conn in removed_connections:
                    source = conn.get("source")
                    target = conn.get("target")
                    if (source, target) not in existing_connections and (target, source) not in existing_connections:
                        missing_connections.append(f"{source}-{target}")
                
                if missing_connections:
                    return f"Error: Cannot remove non-existent connections: {', '.join(missing_connections)}", None
                
                # Perform actual removals
                success_nodes = []
                for node_id in removed_nodes:
                    if diagram_manager.remove_node(node_id):
                        success_nodes.append(node_id)
                
                success_connections = []
                for conn in removed_connections:
                    source = conn.get("source")
                    target = conn.get("target")
                    if diagram_manager.remove_connection(source, target):
                        success_connections.append(f"{source}-{target}")
                
                message = "Removed: "
                if success_nodes:
                    message += f"nodes [{', '.join(success_nodes)}] "
                if success_connections:
                    message += f"connections [{', '.join(success_connections)}]"
                return message, None

            # Handle normal diagram updates
            if "nodes" in data or "connections" in data:
                # Check connections reference existing nodes
                existing_node_ids = set(diagram_manager.G.nodes())
                new_node_ids = {node["id"] for node in data.get("nodes", [])}
                all_node_ids = existing_node_ids.union(new_node_ids)
                
                invalid_connections = []
                for conn in data.get("connections", []):
                    source = conn.get("source")
                    target = conn.get("target")
                    if source not in all_node_ids or target not in all_node_ids:
                        invalid_connections.append(f"{source}-{target} (missing nodes)")
                
                if invalid_connections:
                    return f"Error: Cannot create connections with non-existent nodes: {', '.join(invalid_connections)}", None

                # Process nodes
                added_nodes = []
                for node in data.get("nodes", []):
                    try:
                        node_id = node["id"]
                        name = node.get("name", node_id)
                        ntype = node.get("type", "generic").lower()
                        details = node.get("details", {})
                        diagram_manager.add_node(node_id, name, ntype, details)
                        added_nodes.append(node_id)
                    except Exception as e:
                        print(f"[WARNING] Failed to add node {node}: {e}")

                # Process connections
                added_connections = []
                for conn in data.get("connections", []):
                    try:
                        source = conn["source"]
                        target = conn["target"]
                        conn_type = conn.get("type", "standard")
                        if diagram_manager.add_connection(source, target, conn_type):
                            added_connections.append(f"{source}-{target}")
                    except Exception as e:
                        print(f"[WARNING] Failed to add connection {conn}: {e}")

                message = "Updated diagram with: "
                if added_nodes:
                    message += f"nodes [{', '.join(added_nodes)}] "
                if added_connections:
                    message += f"connections [{', '.join(added_connections)}]"
                return message, response

            return "Error: No valid nodes or connections were specified in your command. Please provide more details.", None

        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON decoding failed: {e}")
            return "Error: Couldn't understand the AI's response format. Please try a different command.", None

    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        return f"Error processing command: {str(e)}", None

def create_ui():
    import io
    import tempfile
    from PIL import Image
    import matplotlib.pyplot as plt

    diagram_manager = NetworkDiagramManager()
    history = []

    def handle_command(command, chat_history):
        response, explanation = process_command(command, diagram_manager, chat_history)
        chat_history.append((command, response))
        current_fig = diagram_manager.render_diagram(export=False)
        return chat_history, current_fig, response or "Enter a command to create a network diagram"

    def export_diagram():
        if diagram_manager.G.nodes:
            fig = diagram_manager.render_diagram(export=False)
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight', dpi=300)
            buf.seek(0)
            img = Image.open(buf)
            temp_dir = tempfile.gettempdir()
            file_path = os.path.join(temp_dir, "NetsphereDiagram.png")
            img.save(file_path)
            plt.close(fig)
            return file_path
        return None

    def clear_chat():
        diagram_manager.reset_diagram()
        current_fig = diagram_manager.render_diagram(export=False)
        return [], current_fig, ""

    with gr.Blocks(theme=Soft()) as demo:
        gr.HTML("<title>NetSphere</title>")
        gr.Markdown("# NetSphere")
        gr.Markdown("Create and modify network diagrams using natural language commands.")

        chat_state = gr.State([])

        with gr.Row():
            with gr.Column(scale=1):
                command_input = gr.Textbox(
                    placeholder="e.g., 'Add 2 servers' or 'Connect server1 to router1'",
                    label="Command",
                    lines=1
                )
                
                with gr.Row():
                    submit_btn = gr.Button("Update Diagram", variant="primary")
                
                with gr.Row():
                    export_btn = gr.Button("Export PNG")
                    clear_btn = gr.Button("Clear Diagram", variant="secondary")

                gr.Markdown("""### Example Commands:
- Create a network with a router and 3 computers
- Add a firewall between router and computers
- Add 2 servers in the data layer
- Connect web server to database server
""")

                explanation_box = gr.Textbox(
                    label="Information",
                    interactive=False,
                    lines=15,
                    max_lines=20
                )

            with gr.Column(scale=2):
                diagram_output = gr.Plot(label="Network Diagram")
                export_output = gr.File(label="Download Exported Diagram", visible=True)

        submit_btn.click(
            handle_command,
            inputs=[command_input, chat_state],
            outputs=[chat_state, diagram_output, explanation_box]
        )

        command_input.submit(
            handle_command,
            inputs=[command_input, chat_state],
            outputs=[chat_state, diagram_output, explanation_box]
        )

        export_btn.click(
            export_diagram,
            outputs=export_output
        )

        clear_btn.click(
            clear_chat,
            outputs=[chat_state, diagram_output, explanation_box]
        )

    return demo

# Launch the Gradio interface
if __name__ == "__main__":
    demo = create_ui()
    demo.launch()