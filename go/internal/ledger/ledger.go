package ledger

import (
	"fmt"
	"sync"
	"time"
)

// LockEntry tracks the current owner of a task/resource lock.
type LockEntry struct {
	AgentID   string
	Timestamp time.Time
}

// Ledger is the in-memory synchronization primitive for the Go port.
type Ledger struct {
	mu    sync.RWMutex
	locks map[string]LockEntry
}

// New creates an empty ledger.
func New() *Ledger {
	return &Ledger{
		locks: make(map[string]LockEntry),
	}
}

// Lock claims a task/resource for an agent, mirroring the Python contract.
func (l *Ledger) Lock(taskID, agentID string) error {
	l.mu.Lock()
	defer l.mu.Unlock()

	if current, ok := l.locks[taskID]; ok && current.AgentID != agentID {
		return fmt.Errorf("task %q is locked by %s", taskID, current.AgentID)
	}

	l.locks[taskID] = LockEntry{
		AgentID:   agentID,
		Timestamp: time.Now().UTC(),
	}
	return nil
}

// Unlock releases a task/resource lock.
func (l *Ledger) Unlock(taskID string) error {
	l.mu.Lock()
	defer l.mu.Unlock()

	if _, ok := l.locks[taskID]; !ok {
		return fmt.Errorf("task %q is not locked", taskID)
	}

	delete(l.locks, taskID)
	return nil
}

// Snapshot returns a copy of the current lock table for inspection/testing.
func (l *Ledger) Snapshot() map[string]LockEntry {
	l.mu.RLock()
	defer l.mu.RUnlock()

	snapshot := make(map[string]LockEntry, len(l.locks))
	for taskID, entry := range l.locks {
		snapshot[taskID] = entry
	}
	return snapshot
}
