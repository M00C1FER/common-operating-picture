package attestation

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

// TaskAttestation signs task payloads with HMAC-SHA256.
type TaskAttestation struct {
	SignerID string
	secret   []byte
}

// NewTaskAttestation creates a signer/verifier for task attestations.
func NewTaskAttestation(signerID, secret string) *TaskAttestation {
	return &TaskAttestation{
		SignerID: signerID,
		secret:   []byte(secret),
	}
}

// Sign returns a hex-encoded HMAC over task metadata and payload JSON.
func (t *TaskAttestation) Sign(taskID string, payload any) (string, error) {
	body, err := canonicalJSON(payload)
	if err != nil {
		return "", err
	}

	mac := hmac.New(sha256.New, t.secret)
	if _, err := mac.Write([]byte(taskID)); err != nil {
		return "", err
	}
	if _, err := mac.Write([]byte(":")); err != nil {
		return "", err
	}
	if _, err := mac.Write([]byte(t.SignerID)); err != nil {
		return "", err
	}
	if _, err := mac.Write([]byte(":")); err != nil {
		return "", err
	}
	if _, err := mac.Write(body); err != nil {
		return "", err
	}

	return hex.EncodeToString(mac.Sum(nil)), nil
}

// Verify recomputes and compares the signature for the supplied payload.
func (t *TaskAttestation) Verify(taskID string, payload any, signature string) (bool, error) {
	expected, err := t.Sign(taskID, payload)
	if err != nil {
		return false, err
	}

	provided, err := hex.DecodeString(signature)
	if err != nil {
		return false, fmt.Errorf("decode signature: %w", err)
	}

	want, err := hex.DecodeString(expected)
	if err != nil {
		return false, fmt.Errorf("decode expected signature: %w", err)
	}

	return hmac.Equal(provided, want), nil
}

func canonicalJSON(payload any) ([]byte, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal payload: %w", err)
	}
	return body, nil
}
