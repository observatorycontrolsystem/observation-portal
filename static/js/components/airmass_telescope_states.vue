<template>
  <div class="airmassTelescopeStatesCombo">
    <airmass ref="airmass" v-on:rangechanged="updateTelescopeStatesRange" :data="airmassData" v-show="'airmass_limit' in airmassData" :showZoomControls="true" :alignleft="true"></airmass>
    <p></p>
    <telescope_states ref="telescope_states" v-on:rangechanged="updateAirmassRange" :data="telescopeStatesData" :activeObservation="activeObservation" v-show="'airmass_limit' in airmassData" :showZoomControls="false"></telescope_states>
    <div class="visibilityHistoryPlotLegend text-center">
      <ul class="list-inline mt-1">
        <li class="list-inline-item">
          <span class="legend-item AVAILABLE align-middle mb-1 mr-1"></span>
          Available
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item NOT_OK_TO_OPEN align-middle mb-1 mr-1"></span>
          Weather
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item SEQUENCER_DISABLED align-middle mb-1 mr-1"></span>
          Manually Disabled
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item NO_CONNECTION align-middle mb-1 mr-1"></span>
          No Connection to Telescope
        </li>
      </ul>
    </div>
  </div>
</template>
<script>
  import airmass from './airmass.vue';
  import telescope_states from './telescope_states.vue';

  export default {
    props: ['airmassData', 'telescopeStatesData', 'activeObservation'],
    components: {airmass, telescope_states},
    data: function(){
      return {};
    },
    methods: {
      updateAirmassRange: function(window) {
        this.$refs.airmass.updateWindow(window);
      },
      updateTelescopeStatesRange: function(window) {
        this.$refs.telescope_states.updateWindow(window);
      }
    },
  };
</script>
