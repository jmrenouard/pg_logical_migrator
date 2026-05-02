# Bash completion for pg_migrator.py

_pg_migrator_completion() {
    local cur prev opts subcmds
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Global options
    opts="-h --help -V --version -c --config --results-dir --loglevel --log-file --sync-delay -n --dry-run -v --verbose --use-stats"
    
    # Subcommands
    subcmds="check diagnose params migrate-schema-pre-data setup-pub setup-sub repl-progress refresh-matviews sync-sequences terminate-repl sync-lobs enable-triggers reassign-owner audit-objects validate-rows cleanup setup-reverse progress wait-sync cleanup-reverse init-replication post-migration tui generate-config"

    # If the previous word is an option that expects a value
    case "${prev}" in
        -c|--config|--results-dir|--log-file|-o|--output)
            COMPREPLY=( $(compgen -f -- "${cur}") )
            return 0
            ;;
        --loglevel)
            COMPREPLY=( $(compgen -W "DEBUG INFO WARNING ERROR CRITICAL" -- "${cur}") )
            return 0
            ;;
    esac

    # If we are completing a subcommand or a global option
    if [[ ${cur} == -* ]] ; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    # Check if a subcommand is already present in the command line
    local subcmd_found=""
    for word in "${COMP_WORDS[@]:1:COMP_CWORD-1}"; do
        if [[ " ${subcmds} " =~ " ${word} " ]]; then
            subcmd_found="${word}"
            break
        fi
    done

    if [[ -z "${subcmd_found}" ]]; then
        # Complete subcommands
        COMPREPLY=( $(compgen -W "${subcmds}" -- "${cur}") )
    else
        # Complete options specific to the subcommand
        case "${subcmd_found}" in
            migrate-schema-pre-data|init-replication)
                COMPREPLY=( $(compgen -W "--drop-dest ${opts}" -- "${cur}") )
                ;;
            reassign-owner)
                COMPREPLY=( $(compgen -W "--owner ${opts}" -- "${cur}") )
                ;;
            generate-config)
                COMPREPLY=( $(compgen -W "-o --output ${opts}" -- "${cur}") )
                ;;
            *)
                COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
                ;;
        esac
    fi

    return 0
}

complete -F _pg_migrator_completion pg_migrator.py
complete -F _pg_migrator_completion ./pg_migrator.py
