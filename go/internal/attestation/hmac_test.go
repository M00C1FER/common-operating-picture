package attestation

import "testing"

func TestSignAndVerify(t *testing.T) {
	ta := NewTaskAttestation("agent-a", "shared-secret")
	payload := map[string]string{
		"owner":       "agent-a",
		"acquired_at": "2026-05-01T00:00:00Z",
	}

	signature, err := ta.Sign("task-1", payload)
	if err != nil {
		t.Fatalf("Sign() error = %v", err)
	}

	ok, err := ta.Verify("task-1", payload, signature)
	if err != nil {
		t.Fatalf("Verify() error = %v", err)
	}
	if !ok {
		t.Fatal("expected signature verification to succeed")
	}
}

func TestVerifyRejectsModifiedPayload(t *testing.T) {
	ta := NewTaskAttestation("agent-a", "shared-secret")
	signature, err := ta.Sign("task-1", map[string]string{"owner": "agent-a"})
	if err != nil {
		t.Fatalf("Sign() error = %v", err)
	}

	ok, err := ta.Verify("task-1", map[string]string{"owner": "agent-b"}, signature)
	if err != nil {
		t.Fatalf("Verify() error = %v", err)
	}
	if ok {
		t.Fatal("expected verification to fail for modified payload")
	}
}
