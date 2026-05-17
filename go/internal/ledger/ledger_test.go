package ledger

import "testing"

func TestLockUnlock(t *testing.T) {
	l := New()

	if err := l.Lock("task-1", "agent-a"); err != nil {
		t.Fatalf("Lock() error = %v", err)
	}

	if err := l.Unlock("task-1"); err != nil {
		t.Fatalf("Unlock() error = %v", err)
	}

	if got := len(l.Snapshot()); got != 0 {
		t.Fatalf("expected empty snapshot, got %d entries", got)
	}
}

func TestLockDeniedForDifferentAgent(t *testing.T) {
	l := New()

	if err := l.Lock("task-1", "agent-a"); err != nil {
		t.Fatalf("first Lock() error = %v", err)
	}

	if err := l.Lock("task-1", "agent-b"); err == nil {
		t.Fatal("expected second agent lock attempt to fail")
	}
}

func TestSameAgentCanReacquire(t *testing.T) {
	l := New()

	if err := l.Lock("task-1", "agent-a"); err != nil {
		t.Fatalf("first Lock() error = %v", err)
	}

	if err := l.Lock("task-1", "agent-a"); err != nil {
		t.Fatalf("same agent re-lock should succeed, got %v", err)
	}
}
