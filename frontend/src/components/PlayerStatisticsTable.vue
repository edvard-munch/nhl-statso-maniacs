<script setup lang="ts">
import { computed } from 'vue';
import type { StatisticsPacket } from '../api/index.js';
import { AVAILABILITY_LABELS } from '../games/presentation.js';
import { FIELD_LABELS, SKATER_FIELDS, GOALIE_FIELDS } from '../players/catalogue.js';
import { profileStatisticLabel } from '../players/profile.js';

const props = defineProps<{
  caption: string;
  kind: 'skater' | 'goalie';
  rows: (StatisticsPacket & { label: string })[];
}>();
const columns = computed(() => (props.kind === 'goalie' ? GOALIE_FIELDS : SKATER_FIELDS));
</script>

<template>
  <div class="table-scroll" role="region" :aria-label="caption" tabindex="0">
    <table class="roster-table">
      <caption>
        {{
          caption
        }}<template v-if="kind === 'skater'"> · TOI per game (mm:ss)</template>
      </caption>
      <thead>
        <tr>
          <th scope="col">Statistics</th>
          <th scope="col">Availability</th>
          <th v-for="field in columns" :key="field" scope="col">
            {{
              field === 'save_percentage'
                ? 'Save %'
                : (FIELD_LABELS[field] || field).replace(' (seconds)', '')
            }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <th scope="row">{{ row.label }}</th>
          <td>{{ AVAILABILITY_LABELS[row.availability] }}</td>
          <td v-for="field in columns" :key="field">
            {{ profileStatisticLabel(row.stats, field) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
