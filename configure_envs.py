#!/usr/bin/env python
import os
import glob

def configure_env_file(example_path):
    """
    Interactively configures a .env file based on its .env.example template.
    """
    env_path = example_path.replace('.env.example', '.env')
    print(f"--- Configuring {os.path.normpath(env_path)} ---")

    final_env_vars = []
    existing_vars = {}

    # Read existing .env file if it exists, to preserve values
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                existing_vars[key.strip()] = value.strip()

    try:
        with open(example_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                
                key, default_value = line.split('=', 1)
                key = key.strip()
                default_value = default_value.strip()

                # Use existing value as the default if available, otherwise use example value
                current_default = existing_vars.get(key, default_value)

                prompt = f"Enter value for '{key}' [default: {current_default}]: "
                user_input = input(prompt)

                final_value = user_input if user_input else current_default
                final_env_vars.append(f"{key}={final_value}")

        if final_env_vars:
            with open(env_path, 'w') as f:
                f.write('\n'.join(final_env_vars) + '\n')
            print(f"Successfully created/updated {os.path.normpath(env_path)}\n")
        else:
            print(f"No variables found in {example_path}. Skipping.\n")

    except Exception as e:
        print(f"An error occurred while processing {example_path}: {e}\n")


def main():
    """
    Finds all .env.example files in the current directory and its subdirectories
    and initiates the interactive configuration for each.
    """
    print("Starting interactive configuration for .env files...\n")
    
    # Search for .env.example files recursively from the current directory
    try:
        example_files = glob.glob('**/.env.example', recursive=True)

        if not example_files:
            print("No .env.example files found in this project.")
            return

        for example_file in sorted(example_files):
            configure_env_file(example_file)

        print("All .env files have been configured.")
    except KeyboardInterrupt:
        print("\nConfiguration cancelled by user.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
