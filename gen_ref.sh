#!/bin/bash

# ========================================================
# Script Name: gen_ref.sh
# Function: Scan all .md files in current directory and generate ref.md index.
#           excludes README.md and the output file itself.
# ========================================================

# Define output filename
OUTPUT_FILE="ref.md"

# Clear or create output file, and write main title
echo "# Index (Reference)" > "$OUTPUT_FILE"
echo "> Auto-generated at $(date "+%Y-%m-%d %H:%M:%S")" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Define an array to store previous loop's directory path parts
declare -a prev_parts=()

# Initialize file counter for ordered lists
file_count=0

# 1. Find all .md files
# 2. Exclude output file (ref.md) and README.md
# 3. Use LC_ALL=C sort to force ASCII sorting. 
#    This ensures uppercase filenames (e.g., FAQ.md) appear before lowercase subdirectories (e.g., experience).
find . -type f -name "*.md" ! -name "$OUTPUT_FILE" ! -name "README.md" | LC_ALL=C sort | while read -r filepath; do
    
    # Get directory path and filename
    dir_path=$(dirname "$filepath")
    filename=$(basename "$filepath")
    
    # Clean path (remove leading ./)
    # If file is in root, clean_dir_path becomes empty
    if [ "$dir_path" == "." ]; then
        clean_dir_path=""
    else
        clean_dir_path="${dir_path#./}"
    fi

    # Split path by '/' into an array
    IFS='/' read -r -a curr_parts <<< "$clean_dir_path"

    # === Logic: Detect Path Changes ===

    # Calculate the length of the common prefix between current and previous path
    common_len=0
    for ((i=0; i<${#curr_parts[@]} && i<${#prev_parts[@]}; i++)); do
        if [[ "${curr_parts[$i]}" == "${prev_parts[$i]}" ]]; then
            ((common_len++))
        else
            break
        fi
    done

    # Flag to determine if we need to reset the file counter
    reset_counter=false

    # Case A: Entering a new subdirectory or switching branches
    # (e.g., moving from doc/ to doc/tutorial)
    if [[ $common_len -lt ${#curr_parts[@]} ]]; then
        reset_counter=true
        
        # Print headers for the new path levels
        for ((i=common_len; i<${#curr_parts[@]}; i++)); do
            title="${curr_parts[$i]}"
            # Calculate heading level (doc=1, tutorial=2, etc.)
            level=$((i + 1))
            hashes=$(printf "%0.s#" $(seq 1 $level))
            echo -e "\n$hashes $title\n" >> "$OUTPUT_FILE"
        done

    # Case B: Returning to a parent directory
    # (e.g., moving from doc/tutorial/experience back to doc/tutorial)
    elif [[ $common_len -eq ${#curr_parts[@]} ]] && [[ ${#curr_parts[@]} -lt ${#prev_parts[@]} ]]; then
        reset_counter=true
        
        # Reprint the header of the current directory to visually separate it 
        # from the previous subdirectory's content.
        last_idx=$((${#curr_parts[@]} - 1))
        if [ $last_idx -ge 0 ]; then
            title="${curr_parts[$last_idx]}"
            level=$(($last_idx + 1))
            hashes=$(printf "%0.s#" $(seq 1 $level))
            echo -e "\n$hashes $title\n" >> "$OUTPUT_FILE"
        fi
    fi

    # Reset counter if directory changed
    if [ "$reset_counter" = true ]; then
        file_count=0
    fi

    # Increment counter for the current file
    ((file_count++))

    # Write file link with explicit numbering
    # Format: 1. [filename](relative_path)
    echo "$file_count. [$filename]($filepath)" >> "$OUTPUT_FILE"

    # Update prev_parts for the next iteration
    prev_parts=("${curr_parts[@]}")

done

echo "Generation completed! Please check $OUTPUT_FILE"