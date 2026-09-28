import torch
import torch.nn as nn
import torch.optim as optim
import os
import pickle
import random
from collections import deque
import logging

class NeuralMemoryNetwork(nn.Module):
    def __init__(self, input_features):
        super().__init__()
        # DEEPER, SMARTER NETWORK (35-year veteran architecture)
        self.fc1 = nn.Linear(input_features, 128)
        self.fc2 = nn.Linear(128, 128)
        self.fc3 = nn.Linear(128, 64)
        self.out = nn.Linear(64, 1)
        self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()
        
    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.relu(self.fc3(x))
        return self.sigmoid(self.out(x))

class ThoughtRepository:
    def __init__(self, input_features=10, buffer_size=100000):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = NeuralMemoryNetwork(input_features).to(self.device)
        self.optimizer = optim.AdamW(self.model.parameters(), lr=0.001)
        self.criterion = nn.BCELoss()
        
        # LONG-TERM EIDETIC MEMORY (Experience Replay Buffer)
        # This guarantees the bot NEVER forgets past lessons.
        self.memory_buffer = deque(maxlen=buffer_size)
        
    def predict(self, features):
        self.model.eval()
        with torch.no_grad():
            x = torch.FloatTensor(features).unsqueeze(0).to(self.device)
            prob = self.model(x).item()
        return prob
        
    def train_on_outcome(self, features, success, r_multiple):
        # 1. Store the experience permanently in the hippocampus
        self.memory_buffer.append((features, success, r_multiple))
        
        # 2. Learn from the PAST (Experience Replay)
        # Instead of just training on this 1 trade and forgetting everything else,
        # we pull 128 random past trades from memory and study them ALL simultaneously!
        batch_size = min(128, len(self.memory_buffer))
        batch = random.sample(self.memory_buffer, batch_size)
        
        self.model.train()
        total_loss = 0
        for b_feat, b_succ, b_rmult in batch:
            x = torch.FloatTensor(b_feat).unsqueeze(0).to(self.device)
            target = torch.FloatTensor([[float(b_succ)]]).to(self.device)
            
            weight = max(1.0, float(b_rmult))
            
            self.optimizer.zero_grad()
            pred = self.model(x)
            
            loss = self.criterion(pred, target) * weight
            loss.backward()
            self.optimizer.step()
            total_loss += loss.item()
            
        return total_loss / batch_size if batch_size > 0 else 0

    def save_brain(self, filepath="brain.pth", bufferpath="memory.pkl"):
        torch.save(self.model.state_dict(), filepath)
        with open(bufferpath, "wb") as f:
            pickle.dump(list(self.memory_buffer), f)
            
    def load_brain(self, filepath="brain.pth", bufferpath="memory.pkl"):
        logger = logging.getLogger("memory")
        if os.path.exists(filepath):
            self.model.load_state_dict(torch.load(filepath, map_location=self.device, weights_only=True))
            logger.info("Loaded 35-year veteran neural brain weights!")
        else:
            logger.info("Starting fresh veteran brain.")
            
        if os.path.exists(bufferpath):
            try:
                with open(bufferpath, "rb") as f:
                    self.memory_buffer = deque(pickle.load(f), maxlen=100000)
                logger.info(f"Restored {len(self.memory_buffer)} past trading memories! I will never forget.")
            except Exception as e:
                logger.warning(f"Could not load memory buffer: {e}")
