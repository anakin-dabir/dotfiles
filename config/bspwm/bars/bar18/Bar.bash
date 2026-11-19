# This file launch the bar/s

# Function for generating workspaces.yuck file with eww widgets
generate_eww_workspaces() {
    local eww_file monitors count m workspace_name
    local listen_workspaces widgets workspace_widgets

    eww_file="$HOME/.config/bspwm/bars/${main_bar}/workspaces.yuck"
    monitors=$(bspc query -M --names)
    count=0
    listen_workspaces=""
    widgets=""
    workspace_widgets=";; Workspaces Widgets ;;\n"

    printf "%s\n" ";; Workspaces ;;" > "$eww_file"

    for m in $monitors; do
        workspace_name="workspace${count}"
        listen_workspaces="${listen_workspaces}(deflisten ${workspace_name} \"scripts/WorkSpaces $m\")\n"
        widgets="${widgets}           (box :visible { monitor==\"$m\" } (${workspace_name}))\n"
        workspace_widgets="${workspace_widgets}(defwidget ${workspace_name} [] (literal :content ${workspace_name}))\n"
        count=$((count + 1))
    done

    printf "%b" "$listen_workspaces" >> "$eww_file"
    printf "%b" "$workspace_widgets" >> "$eww_file"
    printf "%b" ";; Workspaces Main Widget ;;\n(defwidget workspaces [monitor]\n   (box    :orientation \"v\"\n           :space-evenly \"false\"\n           :valign \"start\"\n$widgets))" >> "$eww_file"
}

generate_eww_workspaces

for m in $(bspc query -M --names); do
    eww -c "$HOME/.config/bspwm/bars/${main_bar}" open bar --id "$m" --arg monitor="$m" --toggle
done

# Auto-hide bar when the focused desktop has a fullscreen window.
# Only acts on state TRANSITIONS — workspace switches with no fullscreen change
# don't trigger any work, avoiding the flicker from eww re-opening on every focus.
(
	last_state=""
	bspc subscribe node_state node_remove node_focus desktop_focus | while read -r _; do
		if bspc query -N -n .fullscreen.local -d focused >/dev/null 2>&1; then
			new_state="hidden"
		else
			new_state="shown"
		fi
		if [ "$new_state" != "$last_state" ]; then
			[ "$new_state" = "hidden" ] && HideBar -h || HideBar -u
			last_state="$new_state"
		fi
	done
) &
