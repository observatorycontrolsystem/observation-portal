<template>
  <div class="telescopeStatesPlot">
    <plotcontrols v-show="showZoomControls" v-on:plotZoom="plotZoom"/>
  </div>
</template>
<script>
  import vis from 'vis';
  import $ from 'jquery';
  import _ from 'lodash';
  import 'vue-style-loader!vis/dist/vis.css';
  import 'vue-style-loader!../../css/plot_style.css';

  import { siteToColor, siteCodeToName } from '../utils.js';
  import plotcontrols from './util/plotcontrols.vue';
  import { plotZoomMixin } from './util/plot_mixins.js';

  export default {
    props: [
      'data', 
      'activeObservation', 
      'showZoomControls'
    ],
    mixins: [
      plotZoomMixin
    ],
    components: {
      plotcontrols
    },
    data: function () {
      let event_types = {
        'AVAILABLE': 'Available',
        'NOT_OK_TO_OPEN': '',
        'SEQUENCER_DISABLED': 'Manually Disabled',
        'SITE_AGENT_UNRESPONSIVE': 'No Connection to Telescope',
        'OFFLINE': 'Manually Disabled',
        'ENCLOSURE_INTERLOCK': '',
        'SEQUENCER_UNAVAILABLE': ''
      };

      let options = {
        groupOrder: 'id',
        stack: false,
        maxHeight: '450px',
        minHeight: '120px',
        align: 'left',
        dataAttributes: ['toggle', 'html'],
        selectable: false,
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
        event_types: event_types,
      };
    },
    computed: {
      toVis: function () {
        let plotSites = new vis.DataSet();
        let visData = new vis.DataSet();

        if (this.data !== undefined) {
          let sorted_telescopes = Object.keys(this.data).sort(function keyOrder(k1, k2) {
            let s1 = k1.split('.')[2];
            let s2 = k2.split('.')[2];

            if (s1 < s2) return -1;
            else if (s1 > s2) return +1;
            else if (k1 < k2) return -1;
            else if (k1 > k2) return +1;
            else return 0;
          });

          let g = 0;
          let used_telescopes = {};
          for (let telescope in sorted_telescopes) {
            let site = sorted_telescopes[telescope].split('.')[0];
            if (!(site in used_telescopes)) {
              used_telescopes[site] = 0;
            }
            used_telescopes[site]++;
            plotSites.add({
              id: g,
              content: siteCodeToName[site] + ' ' + used_telescopes[site],
              title: sorted_telescopes[telescope],
              style: 'color: ' + siteToColor[sorted_telescopes[telescope].split('.')[0]] + ';' +
              'width: 130px;'
            });
            for (let index in this.data[sorted_telescopes[telescope]]) {
              let event = this.data[sorted_telescopes[telescope]][index];
              let reason = '';
              if (event['event_type'] === 'NOT_OK_TO_OPEN' || event['event_type'] === 'ENCLOSURE_INTERLOCK') {
                reason = event['event_reason'];
              }
              else if (event['event_type'] === 'SEQUENCER_UNAVAILABLE') {
                reason = ': Telescope initializing';
              }
              visData.add({
                group: g,
                title: this.event_types[event['event_type']] + reason + '<br/>start: ' + event['start'].replace('T', ' ')
                + '<br/>end: ' + event['end'].replace('T', ' '),
                className: event['event_type'],
                start: event['start'],
                end: event['end'],
                toggle: 'tooltip',
                html: true,
                type: 'range'
              });
            }
            if (this.activeObservation !== null && this.activeObservation.site === site && this.activeObservation.enclosure === sorted_telescopes[telescope].split('.')[1] && this.activeObservation.telescope === sorted_telescopes[telescope].split('.')[2]) {
              visData.add({
                group: g,
                title: this.activeObservation.state.toLowerCase() + ' at ' + sorted_telescopes[telescope] + '<br/>start: ' + this.activeObservation.start +
                '<br/>end: ' + this.activeObservation.end,
                className: this.activeObservation.state,
                start: this.activeObservation.start,
                end: this.activeObservation.end,
                toggle: 'tooltip',
                html: true,
                type: 'range'
              });
            }
            g++;
          }
        }
        return {'datasets': visData, 'groups': plotSites};
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
      }
    },
    mounted: function () {
      this.plot = this.buildPlot();
    },
    methods: {
      buildPlot: function () {
        // Set a unique name for the plot element, since vis.js needs this to separate plots
        this.$el.setAttribute('class', _.uniqueId(this.$el.className));
        let plot = new vis.Timeline(this.$el, new vis.DataSet([]), this.options);
        let that = this;
        plot.on('rangechanged', function () {
          that.$emit('rangechanged', that.plot.getWindow());
        });
        return plot;
      }
    }
  };
</script>
