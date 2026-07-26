package main

import (
	"fmt"
	"os"
	"strings"
	"unicode"
)

const usage = `cara-tool - small example CLI bundled with the Cara sandbox

Usage:
  cara-tool hello [name]
  cara-tool upper <text>
  cara-tool slug <text>
  cara-tool version`

func main() {
	if len(os.Args) < 2 {
		fail(usage)
	}

	command := os.Args[1]
	arguments := os.Args[2:]
	switch command {
	case "hello":
		name := "sandbox"
		if len(arguments) > 0 {
			name = strings.Join(arguments, " ")
		}
		fmt.Printf("Hello, %s!\n", name)
	case "upper":
		requireText(command, arguments)
		fmt.Println(strings.ToUpper(strings.Join(arguments, " ")))
	case "slug":
		requireText(command, arguments)
		fmt.Println(slug(strings.Join(arguments, " ")))
	case "version":
		fmt.Println("cara-tool 0.1.0")
	case "help", "--help", "-h":
		fmt.Println(usage)
	default:
		fail(fmt.Sprintf("unknown command %q\n\n%s", command, usage))
	}
}

func requireText(command string, arguments []string) {
	if len(arguments) == 0 {
		fail(fmt.Sprintf("%s requires text", command))
	}
}

func slug(text string) string {
	var result strings.Builder
	pendingDash := false
	for _, character := range strings.ToLower(text) {
		if unicode.IsLetter(character) || unicode.IsDigit(character) {
			if pendingDash && result.Len() > 0 {
				result.WriteByte('-')
			}
			result.WriteRune(character)
			pendingDash = false
		} else {
			pendingDash = true
		}
	}
	return result.String()
}

func fail(message string) {
	fmt.Fprintln(os.Stderr, message)
	os.Exit(2)
}
