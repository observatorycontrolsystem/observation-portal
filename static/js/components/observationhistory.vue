<template>
  <div>
    <div class="observationHistoryPlot" id="plot">
      <plotcontrols v-show="showZoomControls" v-on:plotZoom="plotZoom"></plotcontrols>
    </div>
    <div class="observationHistoryPlotLegend text-center">
      <ul class="list-inline mt-1">
        <li class="list-inline-item">
          <span class="legend-item CANCELED align-middle mb-1 mr-1"></span>
          Superseded by new schedule
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item SCHEDULED align-middle mb-1 mr-1"></span>
          Scheduled
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item NOT_ATTEMPTED align-middle mb-1 mr-1"></span>
          Not Attempted
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item IN_PROGRESS align-middle mb-1 mr-1"></span>
          In Progress
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item FAILED align-middle mb-1 mr-1"></span>
          Failed
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item ABORTED align-middle mb-1 mr-1"></span>
          Aborted
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item PARTIALLY-COMPLETED align-middle mb-1 mr-1"></span>
          Partially Completed
        </li>
        <li class="list-inline-item ml-3">
          <span class="legend-item COMPLETED align-middle mb-1 mr-1"></span>
          Completed
        </li>
      </ul>
    </div>
  </div>
</template>
<script>
  import vis from 'vis';
  import $ from 'jquery';
  import _ from 'lodash';
  import 'vue-style-loader!vis/dist/vis.css';
  import 'vue-style-loader!../../css/plot_style.css';
  import plotcontrols from './util/plotcontrols.vue';
  import {plotZoomMixin} from './util/plot_mixins.js';

  export default {
    props: ['data', 'showZoomControls'],
    mixins: [plotZoomMixin],
    components: {plotcontrols},
    data: function () {
      let options = {
        groupOrder: 'content',
        maxHeight: '450px',
        minHeight: '120px',
        align: 'right',
        dataAttributes: ['toggle', 'html'],
        selectable: false,
        snap: null,
        zoomKey: 'ctrlKey',
        moment: function (date) {
          return vis.moment(date).utc();
        },
        tooltip: {
          overflowMethod: 'cap',
        }
      };
      return {
        options: options,
        plotItemToObservationIds: {},
      };
    },
    computed: {
      toVis: function () {
        let visGroups = new vis.DataSet();
        let visData = new vis.DataSet();
        let timeline_min = 0;
        let timeline_max = 0;
        if(this.data.length > 0) {
          let previousObservation = this.data[0];
          let previousObservationIndex = 1;
          let index = 0;
          for (let i = 0; i < this.data.length; i++) {
            let observation = this.data[i];
            let state = observation.state;
            if (state === 'PENDING'){
              if (new Date(observation.end) > new Date()){
                state = 'SCHEDULED';
              }
              else{
                state = 'NOT_ATTEMPTED';
              }
            }
            if (state != 'COMPLETED' && new Date(observation.end) < new Date() && observation.percent_completed > 0){
              state = 'PARTIALLY-COMPLETED';
            }
            observation.state = state;

            if (observation.fail_reason !== '') {
              observation.fail_reason = '<br/>reason: ' + observation.fail_reason;
            }
            if (observation.percent_completed > 0) {
              observation.percent_completed = '<br/>percent completed: ' + observation.percent_completed.toFixed(1);
            }
            else {
              observation.percent_completed = '';
            }
            if (observation.start !== previousObservation.start || observation.site !== previousObservation.site || observation.state !== previousObservation.state
              || observation.enclosure !== previousObservation.enclosure || observation.telescope !== previousObservation.telescope) {
              let className = 'timeline_observation ' + previousObservation.state;
              this.plotItemToObservationIds[index] = previousObservation.id;
              visGroups.add({id: index, content: previousObservationIndex});
              visData.add({
                id: index,
                group: index,
                title: 'telescope: ' + previousObservation.site + '.' + previousObservation.enclosure + '.' + previousObservation.telescope + previousObservation.percent_completed + previousObservation.fail_reason + '<br/>start: ' + previousObservation.start.replace('T', ' ') + '<br/>end: ' + previousObservation.end.replace('T', ' '),
                className: className,
                start: previousObservation.start,
                end: previousObservation.end,
                toggle: 'tooltip',
                html: true,
                type: 'range'
              });
              index++;
              previousObservationIndex = i + 1;
            }
            previousObservation = observation;
          }
          this.plotItemToObservationIds[index] = previousObservation.id;
          visGroups.add({id: index, content: previousObservationIndex});
          visData.add({
            id: index,
            group: index,
            title: 'telescope: ' + previousObservation.site + '.' + previousObservation.enclosure + '.' + previousObservation.telescope + previousObservation.percent_completed + previousObservation.fail_reason + '<br/>start: ' + previousObservation.start.replace('T', ' ') + '<br/>end: ' + previousObservation.end.replace('T', ' '),
            className: 'timeline_observation ' + previousObservation.state,
            start: previousObservation.start,
            end: previousObservation.end,
            toggle: 'tooltip',
            html: true,
            type: 'range'
          });
          index++;
          timeline_min = new Date(visData.get(index - 1)['start']);
          timeline_max = new Date(visData.get(index - 1)['end']);
          if (index > 12) {
            for (let k = index - 1; k >= index - 12; k--) {
              let start = new Date(visData.get(k)['start']);
              let end = new Date(visData.get(k)['end']);
              if (start < timeline_min) {
                timeline_min = start;
              }
              if (end > timeline_max) {
                timeline_max = end;
              }
            }
            timeline_max.setMinutes(timeline_max.getMinutes() + 30);
            timeline_min.setMinutes(timeline_min.getMinutes() - 30);
          }
        }
        return {datasets: visData, groups: visGroups, window: {start: timeline_min, end: timeline_max}};
      }
    },
    watch: {
      data: function () {
        let datasets = this.toVis;
        //Need to first zero out the items and groups or vis.js throws an error
        this.plot.setItems(new vis.DataSet());
        this.plot.setGroups(new vis.DataSet());
        this.plot.setGroups(datasets.groups);
        this.plot.setItems(datasets.datasets);
        this.plot.setWindow(datasets.window.start, datasets.window.end);
      }
    },
    mounted: function () {
      this.plot = this.buildPlot();
      let that = this;
      this.plot.on('click', function(event) {
        let observationId = that.plotItemToObservationIds[event.item];
        if (observationId) {
          window.location.assign('/observations/' + observationId);
        }
      })
    },
    methods: {
      buildPlot: function () {
        // Set a unique name for the plot element, since vis.js needs this to separate plots
        this.$el.setAttribute('class', _.uniqueId(this.$el.className));
        return new vis.Timeline(document.getElementById('plot'), new vis.DataSet([]), this.options);
      }
    }
  };
</script>
