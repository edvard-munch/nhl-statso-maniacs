<script setup lang="ts">
import { computed } from 'vue';
import type { GameGoalie, GameSkater } from '../api/index.js';
import {
  AVAILABILITY_LABELS,
  UNAVAILABLE,
  numberLabel,
  savePercentageLabel,
  toiLabel,
} from '../games/presentation.js';

type Props = { caption: string } & (
  { kind: 'skater'; players: GameSkater[] } | { kind: 'goalie'; players: GameGoalie[] }
);
const props = defineProps<Props>();
const SKATER_COLUMNS = [
  ['G', 'Goals'],
  ['A', 'Assists'],
  ['P', 'Points'],
  ['+/-', 'Plus/minus'],
  ['PIM', 'Penalty minutes'],
  ['SOG', 'Shots on goal'],
  ['Hits', 'Hits'],
  ['Blk', 'Blocked shots'],
  ['FW', 'Faceoffs won'],
  ['PPP', 'Power-play points'],
  ['SHP', 'Short-handed points'],
  ['TOI', 'Time on ice'],
  ['PP TOI', 'Power-play time on ice'],
  ['SH TOI', 'Short-handed time on ice'],
] as const;
const GOALIE_COLUMNS = [
  ['Dec', 'Decision'],
  ['TOI', 'Time on ice'],
  ['GA', 'Goals against'],
  ['SV', 'Saves'],
  ['SA', 'Shots against'],
  ['SV%', 'Save percentage'],
  ['SO', 'Shutouts'],
] as const;
const columns = computed(() => (props.kind === 'skater' ? SKATER_COLUMNS : GOALIE_COLUMNS));
const rows = computed(() => {
  if (props.kind === 'skater')
    return props.players.map((player) => ({
      player,
      values: [
        numberLabel(player.stats.goals),
        numberLabel(player.stats.assists),
        numberLabel(player.stats.points),
        numberLabel(player.stats.plus_minus),
        numberLabel(player.stats.penalty_minutes),
        numberLabel(player.stats.shots_on_goal),
        numberLabel(player.stats.hits),
        numberLabel(player.stats.blocked_shots),
        numberLabel(player.stats.faceoffs_won),
        numberLabel(player.stats.pp_points),
        numberLabel(player.stats.sh_points),
        toiLabel(player.stats.toi_seconds),
        toiLabel(player.stats.pp_toi_seconds),
        toiLabel(player.stats.sh_toi_seconds),
      ],
    }));
  return props.players.map((player) => ({
    player,
    values: [
      player.stats.decision ?? UNAVAILABLE,
      toiLabel(player.stats.toi_seconds),
      numberLabel(player.stats.goals_against),
      numberLabel(player.stats.saves),
      numberLabel(player.stats.shots_against),
      savePercentageLabel(player.stats.save_percentage),
      numberLabel(player.stats.shutouts),
    ],
  }));
});
</script>

<template>
  <div v-if="!players.length" class="empty-roster">
    <h3>{{ caption }}</h3>
    <p>No saved players in this roster group.</p>
  </div>
  <div v-else class="table-scroll" role="region" :aria-label="caption" tabindex="0">
    <table class="roster-table">
      <caption>
        {{
          caption
        }}
      </caption>
      <thead>
        <tr>
          <th scope="col">Player</th>
          <th scope="col"><abbr title="Game sweater number">#</abbr></th>
          <th scope="col"><abbr title="Game position">Pos</abbr></th>
          <th scope="col">Availability</th>
          <th v-for="[label, title] in columns" :key="title" scope="col">
            <abbr :title="title">{{ label }}</abbr>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="`${row.player.player_type}:${row.player.nhl_id}`"
          :data-player-type="row.player.player_type"
          :data-nhl-id="row.player.nhl_id"
        >
          <th scope="row">{{ row.player.name }}</th>
          <td>{{ numberLabel(row.player.sweater_number) }}</td>
          <td>{{ row.player.game_position ?? UNAVAILABLE }}</td>
          <td>{{ AVAILABILITY_LABELS[row.player.availability] }}</td>
          <td v-for="(value, index) in row.values" :key="index">{{ value }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
