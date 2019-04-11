<template>
  <div class="airmassTelescopeStatesCombo">
    <airmass ref="airmass" v-on:rangechanged="updateTelescopeStatesRange" :data="airmassData" v-show="'airmass_limit' in airmassData" :showZoomControls="true" :alignleft="true"></airmass>
    <p></p>
    <telescope_states ref="telescope_states" v-on:rangechanged="updateAirmassRange" :data="telescopeStatesData" :activeBlock="activeBlock" v-show="'airmass_limit' in airmassData" :showZoomControls="false"></telescope_states>
    <div class="visibilityHistoryPlotLegend text-center">
      <ul class="list-inline">
        <li class="AVAILABLE legend-item"></li>
        <li>Available</li>
        <li class="NOT_OK_TO_OPEN legend-item"></li>
        <li>Weather</li>
        <li class="SEQUENCER_DISABLED legend-item"></li>
        <li>Manually Disabled</li>
        <li class="NO_CONNECTION legend-item"></li>
        <li>No Connection to Telescope</li>
      </ul>
    </div>
  </div>
</template>
<script>
  import airmass from './airmass.vue';
  import telescope_states from './telescope_states.vue';

  export default {
    props: ['airmassData', 'telescopeStatesData', 'activeBlock'],
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
