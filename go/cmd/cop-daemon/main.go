// cop-daemon: Go port of the common-operating-picture ledger daemon.
// Replaces fcntl-based locking with sync.RWMutex for cross-platform compatibility.
// Python implementation remains in python/ for backward compatibility.
package main

import "fmt"

func main() {
	fmt.Println("cop-daemon stub - see internal/ledger for implementation")
}
